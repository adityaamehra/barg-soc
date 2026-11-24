"""Random programs on the assembled RTL against the instruction-level model.

    python3 demos/simt-gpu/fuzz_rtl.py [--programs N] [--seed S] [--jobs J] [--gfx] [-v]

--gfx fuzzes the graphics design (gfx/rtl/ over rtl/, as run_rtl.py --gfx).

Each program is random but legal and race-free: every one of the 16 threads (4 warps x 4 lanes) works on its own memory, the
divergent code is nested if/else and data-dependent loops built with split/join and vote, and the cross-warp traffic goes
through shared memory between two barriers. The program ends with every thread storing its registers to global memory. The
same bytes go to the model and, through the host bus, to the RTL; the global and shared memory afterwards must be identical.
Random programs reach what the six kernels do not: every RV32IM opcode on odd values, mixed-size loads and stores in every
bank pattern, nested divergence, shuffles with out-of-range sources, tensor ops after divergence, and so on.
"""

from __future__ import annotations

import argparse
import random
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "model"))
import run_rtl  # noqa: E402
import simt  # noqa: E402
from asm import Asm, enc_b, enc_i, enc_r, enc_s  # noqa: E402

if os.environ.get("FUZZ_GFX"):                 # the graphics design (set by --gfx, inherited by the worker processes)
    run_rtl.GFX = True
if os.environ.get("FUZZ_RTL"):                 # fuzz another copy of the RTL (the mutation check below)
    run_rtl.RTL = Path(os.environ["FUZZ_RTL"])

G, S = 0x1000_0000, 0x2000_0000
GP, GI = G + 0x000, G + 0x400            # per-thread private (64 B each) and word-interleaved scratch, global
OUT = G + 0x1000                         # 16 threads x 128 B
SP, SI, SX = S + 0x000, S + 0x400, S + 0x800   # shared: private, interleaved, exchange (16 words)
DUMP = [(GP, 0x800), (OUT, 0x800), (S, 0x840)]   # what the host reads back: (address, bytes)

FREE = list(range(5, 22)) + [25, 30, 1, 3, 4]   # data registers; x22..x24 are loop counters (one per depth), x31 a scratch
PTR_G, PTR_O, PTR_S, TMP = 26, 27, 28, 29

R_OPS = ["add", "sub", "sll", "slt", "sltu", "xor", "srl", "sra", "or_", "and_",
         "mul", "mulh", "mulhsu", "mulhu", "div", "divu", "rem", "remu"]
I_OPS = ["addi", "slti", "sltiu", "xori", "ori", "andi"]
SH_OPS = ["slli", "srli", "srai"]
INTERESTING = [0, 1, 2, 3, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, 0xFFFFFFFE, 0x55555555, 0xAAAAAAAA, 0x12345678, 0xDEADBEEF, 31, 32, 255, 256]


class Gen:
    def __init__(self, rng: random.Random, warps: int | None = None):
        self.rng, self.a, self.n = rng, Asm(), 0
        self.warps = warps if warps is not None else rng.choice([4, 4, 4, 3, 2, 1])

    def reg(self):
        return self.rng.choice(FREE)

    def uniq(self, p):
        self.n += 1
        return f"{p}{self.n}"

    # ---- statements
    def alu(self):
        r, a = self.rng, self.a
        k = r.random()
        if k < 0.5:
            getattr(a, r.choice(R_OPS))(self.reg(), self.reg(), self.reg())
        elif k < 0.75:
            getattr(a, r.choice(I_OPS))(self.reg(), self.reg(), r.choice([0, 1, -1, 2047, -2048, r.randrange(-2048, 2048)]))
        elif k < 0.88:
            getattr(a, r.choice(SH_OPS))(self.reg(), self.reg(), r.randrange(32))
        elif k < 0.94:
            a.lui(self.reg(), r.randrange(1 << 20))
        elif k < 0.97:
            a.auipc(self.reg(), r.randrange(1 << 20))
        else:
            a.li(self.reg(), r.choice(INTERESTING + [r.getrandbits(32)]))

    def mem(self):
        r, a = self.rng, self.a
        shared = r.random() < 0.4
        layout = r.random() < 0.5                                   # interleaved or private
        size = r.choice([1, 2, 4, 4])
        slot = r.randrange(16)
        if layout:
            base = PTR_S if shared else PTR_G                       # private: 64 B per thread
            off = r.randrange(0, 64 // size) * size
            ptr = base
        else:
            ptr = TMP                                               # interleaved: slot * 64 + thread * 4 (+ byte)
            base = SI if shared else GI
            a.csrr(TMP, "gtid")
            a.slli(TMP, TMP, 2)
            a.li(31, base + slot * 64)
            a.add(TMP, TMP, 31)
            off = r.randrange(0, 4 // size) * size
        if r.random() < 0.5:
            {1: a.sb, 2: a.sh, 4: a.sw}[size](self.reg(), off, ptr)
        else:
            rd = self.reg()
            if size == 4:
                a.lw(rd, off, ptr)
            elif size == 2:
                (a.lh if r.random() < 0.5 else a.lhu)(rd, off, ptr)
            else:
                (a.lb if r.random() < 0.5 else a.lbu)(rd, off, ptr)

    def csr(self):
        self.a.csrr(self.reg(), self.rng.choice(["tid", "wid", "gtid", "tmask", "karg", "nt", "nw", "nc", "cid", 0xC80, 0xC82]))

    def simt_misc(self):
        r, a = self.rng, self.a
        k = r.random()
        if k < 0.3:
            a.vote(r.choice([simt.VOTE_ANY, simt.VOTE_ALL, simt.VOTE_BALLOT]), self.reg(), self.reg())
        else:
            mode = r.choice([simt.SHFL_IDX, simt.SHFL_XOR, simt.SHFL_UP, simt.SHFL_DOWN])
            amount = self.reg()
            if r.random() < 0.75:                        # a small, lane-dependent amount: the interesting range of up/down/xor
                a.andi(amount, amount, r.choice([1, 3, 7]))
            a.shfl(mode, self.reg(), self.reg(), amount)

    def edge_div(self):
        """The RISC-V division corner cases on every lane: x / 0, -2^31 / -1, and their remainders."""
        a, r = self.a, self.rng
        x, y, d = r.sample(FREE, 3)
        a.li(x, r.choice([0x80000000, 0x80000000, 7, 0xFFFFFFF9, 0]))
        a.li(y, r.choice([0xFFFFFFFF, 0xFFFFFFFF, 0, 0, 2, 0xFFFFFFFE]))
        getattr(a, r.choice(["div", "divu", "rem", "remu"]))(d, x, y)

    def uniform_branch(self, depth: int):
        """A branch of any kind that is uniform across the active lanes (both operands are set by a vote or an li executed under
        the current mask, so lanes that are inactive hold other values: this checks that the unit reads an active lane)."""
        a, r = self.a, self.rng
        x, y = r.sample(FREE, 2)
        a.vote(r.choice([simt.VOTE_ANY, simt.VOTE_ALL, simt.VOTE_BALLOT]), x, self.predicate())
        if r.random() < 0.5:
            a.vote(simt.VOTE_BALLOT, y, self.predicate())
        else:
            a.li(y, r.choice([0, 1, 3, 15, 0xFFFFFFFF, 0x80000000]))
        skip = self.uniq("skip")
        getattr(a, r.choice(["beq", "bne", "blt", "bge", "bltu", "bgeu"]))(x, y, skip)
        self.block(depth + 1, r.randrange(1, 4), False)
        a.label(skip)

    def jumps(self):
        a, r = self.a, self.rng
        if r.random() < 0.5:                             # jal over a filler instruction: rd = pc + 4
            l = self.uniq("jal")
            a.jal(self.reg(), l)
            a.li(self.reg(), 0x77)
            a.label(l)
        else:                                            # auipc + jalr to pc + 12 over a filler: rd = pc + 8
            a.auipc(TMP, 0)
            a.jalr(self.reg(), TMP, 12)
            a.li(self.reg(), 0x77)

    def predicate(self):
        """A register that differs between lanes: a comparison, a bit, or the lane number."""
        r, a = self.rng, self.a
        p = self.reg()
        k = r.random()
        if k < 0.3:
            a.slt(p, self.reg(), self.reg())
        elif k < 0.5:
            a.andi(p, self.reg(), r.choice([1, 2, 4, 3]))
        elif k < 0.7:
            a.csrr(p, "tid"); a.andi(p, p, r.choice([1, 2, 3])); a.xori(p, p, r.randrange(4))
        elif k < 0.85:
            a.csrr(p, "tid"); a.addi(p, p, -r.randrange(4)); a.sltiu(p, p, 1)
        else:
            a.sltu(p, self.reg(), self.reg())
        return p

    def block(self, depth: int, n: int, top: bool):
        for _ in range(n):
            k = self.rng.random()
            if k < 0.40:
                self.alu()
            elif k < 0.58:
                self.mem()
            elif k < 0.64:
                self.csr()
            elif k < 0.72:
                self.simt_misc()
            elif k < 0.76:
                self.edge_div() if self.rng.random() < 0.5 else self.jumps()
            elif k < 0.80 and depth < 3:
                self.uniform_branch(depth)
            elif k < 0.86 and depth < 3:
                self.if_else(depth)
            elif k < 0.91 and depth < 3:
                self.loop(depth)
            elif k < 0.95 and top:
                self.tensor()
            elif top and self.rng.random() < 0.5:
                self.exchange()
            else:
                self.alu()

    def if_else(self, depth: int):
        a, r = self.a, self.rng
        p = self.predicate()
        e, j = self.uniq("else"), self.uniq("join")
        a.split(p)
        a.beqz(p, e)
        self.block(depth + 1, r.randrange(1, 6), False)
        a.j(j)
        a.label(e)
        if r.random() < 0.8:
            self.block(depth + 1, r.randrange(1, 6), False)
        a.label(j)
        a.join()

    def loop(self, depth: int):
        """A data-dependent loop: each lane counts down its own (random, small) counter; runs while any lane has work."""
        a, r = self.a, self.rng
        cnt = self.reg()
        top_, done = self.uniq("loop"), self.uniq("done")
        body_end = self.uniq("skip")
        ctr = 24 - depth
        a.andi(cnt, cnt, r.choice([1, 3, 3]))
        if r.random() < 0.5:
            a.csrr(cnt, "tid")
            a.andi(cnt, cnt, 3)
        a.mv(ctr, cnt)                                   # the body never writes x22..x24
        a.label(top_)
        a.slt(TMP, "zero", ctr)
        a.vote(simt.VOTE_ANY, 31, TMP)
        a.beqz(31, done)
        a.split(TMP)
        a.beqz(TMP, body_end)
        a.addi(ctr, ctr, -1)
        self.block(depth + 1, r.randrange(1, 4), False)
        a.label(body_end)
        a.join()
        a.j(top_)
        a.label(done)

    def tensor(self):
        a, r = self.a, self.rng
        a.mma_zero()
        for _ in range(r.randrange(1, 4)):
            if r.random() < 0.3:
                self.alu()
            a.mma(self.reg(), self.reg())
        if r.random() < 0.3:
            a.mma_st(self.reg(), self.reg())
        for _ in range(r.randrange(1, 4)):
            a.mma_ld(self.reg(), self.reg())

    def exchange(self):
        """Every thread publishes a word, all four warps wait, every thread reads another thread's word, all wait again."""
        a, r = self.a, self.rng
        a.csrr(TMP, "gtid")
        a.slli(TMP, TMP, 2)
        a.li(31, SX)
        a.add(TMP, TMP, 31)
        a.sw(self.reg(), 0, TMP)
        a.li(TMP, r.randrange(4))
        a.li(31, self.warps)
        a.bar(TMP, 31)
        a.li(TMP, SX + 4 * r.randrange(16))
        a.lw(self.reg(), 0, TMP)
        a.li(TMP, r.randrange(4))
        a.li(31, self.warps)
        a.bar(TMP, 31)

    # ---- a faulting instruction (the error programs): the core must stop with the same cause, warp and pc as the model
    def fault(self):
        a, r = self.a, self.rng
        kind = r.choice(["illegal", "illegal", "memory", "memory", "lane_memory", "simt", "tensor", "csr"])
        if kind == "illegal":
            a.raw(r.choice([0x00000000, 0xFFFFFFFF, 0x00000073, 0x00100073, 0x30200073, 0x0000002F, 0x0000100B | 7 << 12,
                            0x0000002B | 4 << 12, enc_r(0x2B, 5, 0, 6, 7, 0), enc_r(0x2B, 5, 2, 6, 7, 0), enc_r(0x2B, 0, 3, 6, 0, 0),
                            enc_r(0x0B, 5, 5, 6, 0, 3), enc_r(0x0B, 5, 6, 6, 7, 5), enc_r(0x0B, 5, 0, 6, 0, 1), 0xCC0 << 20 | 6 << 15 | 1 << 12 | 5 << 7 | 0x73,          # csrrw x5, tid, x6
                            0xCC0 << 20 | 6 << 15 | 2 << 12 | 0 << 7 | 0x73,          # csrrs x0, tid, x6 (a write)
                            enc_r(0x13, 5, 1, 6, 1, 1), enc_r(0x33, 5, 0, 6, 7, 2), enc_b(2, 6, 7, 8),
                            enc_i(0x03, 5, 3, 6, 0), enc_s(0x23, 3, 6, 7, 0)]))
        elif kind == "memory":
            addr, op = r.choice([(GP + 1, "lw"), (GP + 2, "lw"), (GP + 1, "lh"), (GP + 3, "sw"), (GP + 1, "sh"), (G + 0x2000, "lw"),
                                 (G + 0x2000, "sw"), (G + 0x1FFD, "lw"), (S + 0x1000, "lw"), (S + 0x1000, "sb"), (0, "lw"), (0x100, "sw"),
                                 (0x40000000, "lw"), (0x30000000, "lw"), (S + 0xFFF, "lh"), (G - 4, "lw"), (G + 0x1FFC, "sb")])
            a.li(TMP, addr)
            if op[0] == "l":
                getattr(a, op)(self.reg(), 0, TMP)
            else:
                getattr(a, op)(self.reg(), 0, TMP)
        elif kind == "lane_memory":                      # only one lane's address is bad, and only if that lane is active
            k = r.randrange(4)
            a.csrr(TMP, "tid")
            a.addi(TMP, TMP, -k)
            a.sltiu(TMP, TMP, 1)
            a.add(TMP, TMP, PTR_G)                       # misaligned (+1) in lane k only
            p = self.predicate()
            e, j = self.uniq("else"), self.uniq("join")
            a.split(p)
            a.beqz(p, e)
            (a.lw if r.random() < 0.5 else a.sw)(self.reg(), 0, TMP)
            a.j(j)
            a.label(e)
            a.label(j)
            a.join()
        elif kind == "simt":
            what = r.choice(["join", "bar", "bar", "overflow", "overflow"])
            if what == "join":
                a.join()
            elif what == "bar":
                a.li(TMP, r.randrange(4, 9))
                a.li(31, 1)
                a.bar(TMP, 31)
            else:
                a.li(TMP, 1)
                for _ in range(r.choice([8, 9, 9])):    # 8 uniform splits fit, the 9th overflows
                    a.split(TMP)
        elif kind == "tensor":
            p = self.predicate()
            e, j = self.uniq("else"), self.uniq("join")
            a.split(p)
            a.beqz(p, e)
            r.choice([lambda: a.mma(self.reg(), self.reg()), lambda: a.mma_zero(), lambda: a.mma_ld(self.reg(), self.reg()),
                      lambda: a.mma_st(self.reg(), self.reg())])()
            a.j(j)
            a.label(e)
            a.label(j)
            a.join()
        else:
            a.csrr(self.reg(), r.choice([0x7C0, 0xCCF, 0xB00, 0xCC6, 0xFC3, 0xC01, 0xC81, 0x000, 0xFFF]))

    # ---- the program
    def program(self, size: int, faulty: bool = False) -> bytes:
        a, r = self.a, self.rng
        # every warp starts: warp 0 lane 0 spawns the others, then every warp turns on its four lanes
        a.li(5, self.warps)
        a.la(6, "ws")
        a.wspawn(5, 6)
        a.label("ws")
        a.li(5, 15)
        a.tmc(5)
        a.csrr(TMP, "gtid")
        a.slli(PTR_G, TMP, 6)
        a.li(31, GP)
        a.add(PTR_G, PTR_G, 31)
        a.slli(PTR_S, TMP, 6)
        a.li(31, SP)
        a.add(PTR_S, PTR_S, 31)
        a.slli(PTR_O, TMP, 7)
        a.li(31, OUT)
        a.add(PTR_O, PTR_O, 31)
        for x in FREE:                                   # every thread gets its own values
            a.li(x, r.choice(INTERESTING + [r.getrandbits(32)]))
            if r.random() < 0.7:
                a.csrr(TMP, "gtid")
                a.addi(TMP, TMP, r.randrange(1, 9))
                a.mul(x, x, TMP)
        self.block(0, size, True)
        if faulty:
            self.fault()
        for i, x in enumerate(FREE):
            a.sw(x, 4 * i, PTR_O)
        a.tmc("zero")
        return a.assemble()


def gen(seed: int, size: int = 40, faulty: bool = False) -> bytes:
    """A random program that fits the 2 KB instruction memory (smaller and smaller until it does). A faulty program runs on one
    warp (which warp faults first would otherwise depend on the scheduler) and ends in a fault."""
    while True:
        code = Gen(random.Random(seed), warps=1 if faulty else None).program(size, faulty)
        if len(code) <= 2048:
            return code
        size = size * 3 // 4


def cause_of(e: simt.GpuError) -> int:
    """ISA cause code of a model error: 1 illegal, 2 memory, 3 SIMT, 4 tensor, 5 CSR."""
    t = e.reason
    if t.startswith("no CSR"):
        return 5
    if "has no destination" in t or "has no operands" in t:
        return 1                                     # a non-zero field that must be 0: an illegal instruction
    if "tensor" in t:
        return 4
    if any(w in t for w in ("misaligned", "outside data memory", "IPDOM", "join with", "no barrier", "fetch")):
        return 2 if t.startswith(("misaligned", "data access")) else 3
    return 1


def run_model(code: bytes):
    gpu = simt.Gpu(simt.Config())
    gpu.write(0, code)
    gpu.launch(0)
    err = None
    try:
        gpu.run(2_000_000)
    except simt.GpuError as e:
        err = e
    return {a + 4 * k: w for a, n in DUMP for k, w in enumerate(gpu.read_words(a, n // 4))}, gpu.stats.steps, err


def run_limited(cmd: list[str], cwd: Path, max_rss_mb: int = 200, max_seconds: float = 90, max_out_mb: int = 16) -> str | None:
    """Run a simulation with a watchdog: kill it if its memory (RSS) passes max_rss_mb, its output passes max_out_mb or it runs longer
    than max_seconds. A broken design (a combinational loop, a runaway loop) can otherwise grow without bound and take the machine
    down. Output goes to a file, not a pipe. Returns the output, or None if it was killed."""
    out = cwd / "sim.out"
    with out.open("wb") as f:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT)
        start = time.monotonic()
        try:
            while proc.poll() is None:
                time.sleep(0.1)
                rss = subprocess.run(["ps", "-o", "rss=", "-p", str(proc.pid)], capture_output=True, text=True).stdout.strip()
                if (rss and int(rss) > max_rss_mb * 1024 or out.stat().st_size > max_out_mb << 20
                        or time.monotonic() - start > max_seconds):
                    proc.kill()
                    proc.wait()
                    return None
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    return out.read_text(errors="replace")


def run_on_rtl(code: bytes, max_cycles: int = 60_000) -> dict[int, int]:
    code = code + bytes(-len(code) % 4)
    writes = [(4 * k, int.from_bytes(code[4 * k:4 * k + 4], "little")) for k in range(len(code) // 4)]
    if os.environ.get("FUZZ_ZERO_MEMORY"):
        # SRAM macros power up holding nothing defined (the behavioural banks start at 0): the host clears the memories first, as a
        # driver would before a launch.
        writes = [(G + 4 * k, 0) for k in range(0x2000 // 4)] + [(S + 4 * k, 0) for k in range(0x1000 // 4)] + writes
    reads = [a + 4 * k for a, n in DUMP for k in range(n // 4)]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "writes.hex").write_text("".join(f"{a:08x}{d:08x}\n" for a, d in writes))
        (tmp / "reads.hex").write_text("".join(f"{a:08x}\n" for a in reads))
        tb = run_rtl.TB.replace('end else if (!done) $display("TIMEOUT");\n    else begin',
                                'end\n    if (!done && !error) $display("TIMEOUT");\n    else begin')
        (tmp / "tb.v").write_text(tb % {"nw": len(writes) - 1, "nr": len(reads), "start": 0, "max": max_cycles, "trace": ""})
        files = [tmp / "tb.v", *run_rtl.rtl_files()]
        built = subprocess.run(["iverilog", "-g2012", "-o", str(tmp / "sim"), *map(str, files)], capture_output=True, text=True)
        if built.returncode:
            raise AssertionError(built.stderr[:1000])
        out = run_limited(["vvp", str(tmp / "sim")], tmp)
        if out is None:
            return {"fail": "the simulation was killed (memory, output size or time limit)"}
    if "DONE" not in out:
        return {"fail": out.strip()[:200]}
    m = re.search(r"DONE (\d+) (\d+)", out)
    e = re.search(r"^ERROR (\d+) (\d+)$", out, re.M)
    pc = re.search(r"^ERRPC (\d+)$", out, re.M)
    return {"cycles": int(m.group(1)), "diverged_cycles": int(m.group(2)),
            "error": (int(e.group(1)), int(e.group(2)), int(pc.group(1))) if e else None,
            "mem": {int(a): int(v) for a, v in re.findall(r"^R (\d+) (\d+)$", out, re.M)}}


def one(job: tuple[int, bool]) -> dict:
    seed, faulty = job
    r = _one(seed, faulty)
    r["faulty"] = faulty
    return r


def _one(seed: int, faulty: bool) -> dict:
    code = gen(seed, faulty=faulty)
    want, steps, err = run_model(code)
    if err is not None and not faulty:               # a generator bug (illegal program), not an RTL bug
        return {"seed": seed, "status": "skip", "why": str(err)}
    got = run_on_rtl(code)
    if "fail" in got:
        return {"seed": seed, "status": "FAIL", "why": got["fail"]}
    expect = None if err is None else (cause_of(err), err.warp, err.pc)
    if got["error"] != expect:
        return {"seed": seed, "status": "FAIL", "why": f"error status: RTL {got['error']}, model {expect} ({err})"}
    bad = [a for a in want if got["mem"].get(a) != want[a]]
    if bad:
        a = bad[0]
        return {"seed": seed, "status": "FAIL", "why": f"{len(bad)} words differ, first 0x{a:08x}: RTL 0x{got['mem'].get(a, -1) & 0xFFFFFFFF:08x} model 0x{want[a]:08x}"}
    return {"seed": seed, "status": "ok", "cycles": got["cycles"], "steps": steps, "words": len(code) // 4, "faulted": err is not None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--programs", type=int, default=40)
    ap.add_argument("--errors", type=int, default=0, help="also run this many programs that end in a fault")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--gfx", action="store_true", help="fuzz the graphics design (gfx/rtl/ over rtl/)")
    args = ap.parse_args()
    if args.gfx:
        os.environ["FUZZ_GFX"] = "1"
        run_rtl.GFX = True
    jobs = [(x, False) for x in range(args.seed, args.seed + args.programs)] + \
           [(x, True) for x in range(args.seed, args.seed + args.errors)]
    with ProcessPoolExecutor(args.jobs) as pool:
        results = list(pool.map(one, jobs))
    for r in results:
        if args.verbose or r["status"] != "ok":
            r = {**r, "kind": "fault" if r["faulty"] else "normal"}
            print(r)
    ok = [r for r in results if r["status"] == "ok"]
    skipped = [r for r in results if r["status"] == "skip"]
    failed = [r for r in results if r["status"] == "FAIL"]
    print(f"{sum(1 for r in ok if r.get('faulted'))} of them stopped on a fault with the same cause, warp and pc")
    print(f"{len(ok)} programs agree, {len(failed)} differ, {len(skipped)} skipped as illegal "
          f"({sum(r['steps'] for r in ok)} warp instructions)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
