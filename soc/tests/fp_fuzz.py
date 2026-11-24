"""Random FP/integer instruction streams, run on the instruction-level model and on the RTL; the final checksum (memory buffer, FP and integer registers, fflags)
must be equal.   python3 demos/quad-soc/tests/fp_fuzz.py <netlist dir> [--seeds N] [--len L] [--first S]
Hart 0 only. Loads and stores of single and double precision on a 512-byte buffer, arithmetic, conversions, compares and moves on f0..f7 (so that
instructions depend on each other closely), integer instructions in between, and now and then a taken branch over an instruction."""
import argparse, importlib.util, random, struct, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import vlsim  # noqa: E402

GCC = "/home/aura/tools/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc"
OBJCOPY = GCC[:-3] + "objcopy"
spec = importlib.util.spec_from_file_location("iss_s", HERE.parents[1] / "linux-soc" / "iss_s.py")
iss = importlib.util.module_from_spec(spec); sys.modules["iss_s"] = iss; spec.loader.exec_module(iss)

F = [f"f{i}" for i in range(8)]
X = ["t0", "t1", "t2", "a2", "a3"]


def gen(seed: int, n: int) -> str:
    r = random.Random(seed)
    out = [".section .text.init", ".globl _start", "_start:", "  csrr t0, mhartid", "  bnez t0, park", "  li t0, 0x6000", "  csrs mstatus, t0",
           "  la s0, buf", "  li s1, 64"]
    for i in range(8):                                    # f0..f7 from the buffer
        out.append(f"  fld f{i}, {8 * i}(s0)")
    out.append("  li t0, 0x3f800001\n  li t1, 7\n  li t2, 9\n  li a2, 1\n  li a3, 2")
    lab = 0
    for _ in range(n):
        k = r.random()
        fa, fb, fc, fd = (r.choice(F) for _ in range(4))
        x, y = r.choice(X), r.choice(X)
        off4, off8 = 4 * r.randrange(0, 120), 8 * r.randrange(0, 60)
        if k < 0.12: out.append(f"  flw {fd}, {off4}(s0)")
        elif k < 0.22: out.append(f"  fld {fd}, {off8}(s0)")
        elif k < 0.30: out.append(f"  fsw {fa}, {off4}(s0)")
        elif k < 0.38: out.append(f"  fsd {fa}, {off8}(s0)")
        elif k < 0.55: out.append("  " + r.choice(["fadd.s", "fsub.s", "fmul.s", "fadd.d", "fsub.d", "fmul.d", "fsgnj.s", "fsgnjn.d", "fsgnjx.d", "fmin.s", "fmax.d"]) + f" {fd}, {fa}, {fb}")
        elif k < 0.60: out.append("  " + r.choice(["fmadd.s", "fmsub.d", "fnmadd.s", "fnmsub.d"]) + f" {fd}, {fa}, {fb}, {fc}")
        elif k < 0.64: out.append(f"  fdiv.s {fd}, {fa}, {fb}" if r.random() < 0.5 else f"  fsqrt.d {fd}, {fa}")
        elif k < 0.70: out.append("  " + r.choice([f"fcvt.s.d {fd}, {fa}", f"fcvt.d.s {fd}, {fa}", f"fcvt.s.w {fd}, {x}", f"fcvt.d.wu {fd}, {x}", f"fmv.w.x {fd}, {x}"]))
        elif k < 0.76: out.append("  " + r.choice([f"fcvt.w.s {x}, {fa}", f"fcvt.wu.d {x}, {fa}", f"fmv.x.w {x}, {fa}", f"feq.s {x}, {fa}, {fb}", f"flt.d {x}, {fa}, {fb}", f"fclass.d {x}, {fa}"]))
        elif k < 0.84: out.append("  " + r.choice([f"add {x}, {x}, {y}", f"addi {x}, {y}, {r.randrange(-50, 50)}", f"xor {x}, {x}, {y}", f"slli {x}, {y}, {r.randrange(1, 9)}", f"mul {x}, {x}, {y}"]))
        elif k < 0.89: out.append(f"  lw {x}, {off4}(s0)" if r.random() < 0.5 else f"  sw {x}, {off4}(s0)")
        elif k < 0.93: out.append(f"  csrrw {x}, fflags, x0" if r.random() < 0.5 else f"  csrr {x}, frm")
        else:
            lab += 1
            out += [f"  beq {x}, {x}, L{lab}", "  addi t1, t1, 1", f"L{lab}:"]
    out += ["  la s2, buf", "  li a0, 0", "  li a1, 128", "1: lw a4, 0(s2)", "  slli t5, a0, 5", "  xor a0, a0, t5", "  add a0, a0, a4", "  addi a0, a0, 17", "  addi s2, s2, 4",
            "  addi a1, a1, -1", "  bnez a1, 1b"]
    for i in range(8):
        out += [f"  fmv.x.w t3, f{i}", "  slli t5, a0, 5", "  xor a0, a0, t5", "  add a0, a0, t3"]
    out += ["  add a0, a0, t0", "  add a0, a0, t1", "  add a0, a0, t2", "  add a0, a0, a2", "  add a0, a0, a3", "  csrr t4, fflags", "  add a0, a0, t4",
            "  ori a0, a0, 0x10", "  li t6, 0x80FFF000", "  sw a0, 0(t6)", "2: j 2b", "park: j park", ".data", ".balign 8", "buf:"]
    out += [f"  .word 0x{r.getrandbits(32):08x}" for _ in range(128)]
    return "\n".join(out) + "\n"


def build(src: str, d: Path) -> bytes:
    (d / "t.S").write_text(src)
    (d / "l.ld").write_text("ENTRY(_start)\nSECTIONS { . = 0x80000000; .text : { *(.text.init) *(.text*) } .data : { *(.data*) } }\n")
    r = subprocess.run([GCC, "-march=rv32imafdc_zicsr", "-mabi=ilp32d", "-nostdlib", "-nostartfiles", "-static", "-T", str(d / "l.ld"), str(d / "t.S"), "-o", str(d / "t.elf")],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr[:1500])
    subprocess.run([OBJCOPY, "-O", "binary", str(d / "t.elf"), str(d / "t.bin")], check=True)
    b = (d / "t.bin").read_bytes()
    return b + b"\0" * (-len(b) % 4)


def run_iss(b: bytes) -> int:
    m = iss.Machine(b + bytes(16))
    off = 0x80FFF000 - iss.RAM_BASE
    for _ in range(3_000_000):
        m.step()
        if int.from_bytes(m.ram[off:off + 4], "little"):
            return int.from_bytes(m.ram[off:off + 4], "little")
    return -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("netlist", type=Path)
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--first", type=int, default=1)
    ap.add_argument("--len", type=int, default=250)
    a = ap.parse_args()
    exe = vlsim.build(a.netlist, HERE / "isa_quad_tb.v")
    bad = 0
    for seed in range(a.first, a.first + a.seeds):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            b = build(gen(seed, a.len), d)
            want = run_iss(b)
            (d / "t.hex").write_text("".join(f"{w:08x}\n" for (w,) in struct.iter_unpack("<I", b)))
            out = vlsim.run(exe, [f"+HEX={d / 't.hex'}", "+TOHOST=80fff000", "+LIMIT=400000"])
            line = [l for l in out.splitlines() if l.startswith(("PASS", "FAIL"))]
            import re
            m = re.search(r"tohost=(\d+)", line[-1]) if line else None
            got = int(m.group(1)) if m else None
            ok = got == want
            bad += not ok
            print(f"seed {seed}: {'ok' if ok else 'MISMATCH'} model {want:#x} rtl {got if got is None else hex(got)}", flush=True)
            if not ok:
                (HERE / f"fuzz_fail_{seed}.S").write_text(gen(seed, a.len))
    print(f"{a.seeds - bad} of {a.seeds} agree")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
