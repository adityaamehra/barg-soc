"""Four harts drive four GPU cores at the same time, on the quad-core SoC's generated Verilog.

    python3 demos/gpu-cluster/multihart_tests.py <assembled netlist dir> [kernel kernel kernel kernel] [--limit CYCLES] [--corrupt]

Hart h loads kernel h's code and data into core h (slot h, 0x3000_0000 + h * 0x20_0000), starts it, polls its STATUS, and checks its
results against the kernel's reference, all while the other three harts do the same: their writes interleave on the shared bus, and
their STATUS polls and result reads (the bridge answers a read with the previous GPU read, so each read sequence is two reads) are
serialised by a spinlock (amoswap) in RAM, which is what a driver has to do. Each hart records its outcome; hart 0 waits for all four
and writes TOHOST (0x80FFF000): 1 for a pass, else (hart * 10000 + failure code) * 2 + 1. --corrupt flips one expected value of hart 2.
"""
import random, re, struct, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "demos" / "gpu-soc"))
import gpu_tests as gt  # noqa: E402
import run_kernel  # noqa: E402
sys.path.insert(0, str(ROOT / "demos" / "quad-soc" / "tests"))
import vlsim  # noqa: E402

cp = gt.cp
argv = sys.argv[1:]
args = [a for i, a in enumerate(argv) if not a.startswith("--") and not (i and argv[i - 1] == "--limit")]
net = Path(args[0])
KERNELS = (args[1:] + ["vecadd", "reduce", "gemm_i8", "conv2d"])[:4] if len(args) > 1 else ["vecadd", "reduce", "gemm_i8", "conv2d"]
LIMIT = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 20_000_000
M = 0xFFFFFFFF
CRT = (".section .text.init\n.globl _start\n_start:\n  csrr t0, mhartid\n  li sp, 0x80F00000\n  slli t1, t0, 16\n  sub sp, sp, t1\n  call main\n1: j 1b\n")
DONE, FAILW, LOCK = 0x80FF0000, 0x80FF0010, 0x80FF0020


def case(h, name, work):
    import simt
    elf = run_kernel.compile_kernel(name, work)
    syms = run_kernel.load_elf(simt.Gpu(simt.Config()), elf)
    inputs, expected = run_kernel.CASES[name](random.Random(1 + h))
    wr = [(h, gt.soc_addr(a), v) for a, seg in cp.elf_segments(elf) for a, v in gt.words(a, seg)]
    wr += [(h, gt.soc_addr(a), v) for sym, raw in inputs.items() for a, v in gt.words(syms[sym][0], raw)]
    rd = [(h, gt.soc_addr(syms[sym][0] + 4 * i), v & M) for sym, want in expected.items() for i, v in enumerate(want)]
    if "--corrupt" in argv and h == 2:
        rd[0] = (rd[0][0], rd[0][1], rd[0][2] ^ 1)
    return wr, syms["_start"][0], rd


import os
NH = int(os.environ.get("NH", "4"))


def source(wr, starts, rd):
    def arr(name, rows):
        body = ",".join("{" + ",".join(f"0x{v & M:x}u" for v in r) + "}" for r in rows) or "{0,0,0}"
        return f"static const uint32_t {name}[][3] = {{{body}}};\n#define N_{name} {len(rows)}\n"
    return f"""#include <stdint.h>
#define REG(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define TOHOST REG({gt.TOHOST:#x})
#define SLOT(k) ((uint32_t)(k) << 21)
static const uint32_t START[4] = {{{",".join(f"{s:#x}u" for s in starts)}}};
{arr("WR", wr)}{arr("RD", rd)}
static inline uint32_t hartid(void) {{ uint32_t h; __asm__ volatile("csrr %0, mhartid" : "=r"(h)); return h; }}
static void lock(void) {{ while (__atomic_exchange_n((volatile uint32_t *)({LOCK:#x}u), 1u, __ATOMIC_ACQUIRE)) ; }}
static void unlock(void) {{ __atomic_store_n((volatile uint32_t *)({LOCK:#x}u), 0u, __ATOMIC_RELEASE); }}
static uint32_t rd(uint32_t a) {{ lock(); (void)REG(a); uint32_t v = REG(a); unlock(); return v; }}
static void finish(uint32_t h, uint32_t code) {{
    REG({FAILW:#x}u + 4 * h) = code;
    __atomic_fetch_add((volatile uint32_t *)({DONE:#x}u), 1u, __ATOMIC_RELEASE);
    if (h != 0) for (;;) ;
}}
int main(void) {{
    uint32_t h = hartid();
    if (h >= {NH}) for (;;) ;
    for (uint32_t i = 0; i < N_WR; i++) if (WR[i][0] == h) REG(WR[i][1] | SLOT(h)) = WR[i][2];
    REG(0x30000004u | SLOT(h)) = START[h];
    REG(0x30000008u | SLOT(h)) = 0;
    REG(0x30000000u | SLOT(h)) = 1;
    uint32_t st;
    do st = rd(0x3000000Cu | SLOT(h)); while (!(st & 6));
    if (st & 4) finish(h, 1);
    else {{
        uint32_t code = 0;
        for (uint32_t i = 0; i < N_RD && !code; i++) if (RD[i][0] == h && rd(RD[i][1] | SLOT(h)) != RD[i][2]) code = 2 + i;
        finish(h, code);
    }}
    while (*(volatile uint32_t *)({DONE:#x}u) != {NH}) ;
    for (uint32_t k = 0; k < {NH}; k++) if (REG({FAILW:#x}u + 4 * k)) {{ TOHOST = (k * 10000 + REG({FAILW:#x}u + 4 * k)) * 2 + 1; for (;;) ; }}
    TOHOST = 1;
    for (;;) ;
}}
"""


with tempfile.TemporaryDirectory() as t:
    tmp = Path(t)
    wr, starts, rd = [], [], []
    for h, name in enumerate(KERNELS):
        (tmp / f"k{h}").mkdir()
        w, s, r = case(h, name, tmp / f"k{h}")
        wr += w; starts.append(s); rd += r
        print(f"hart {h} drives core {h} with {name}: {len(w)} words to write, {len(r)} results to check", flush=True)
    (tmp / "t.c").write_text(source(wr, starts, rd))
    (tmp / "crt.S").write_text(CRT)
    (tmp / "link.ld").write_text(gt.LINK)
    gcc = run_kernel.GCC
    r = subprocess.run([gcc, "-march=rv32imac_zicsr", "-mabi=ilp32", "-O2", "-ffreestanding", "-nostdlib", "-nostartfiles", "-static",
                        "-T", str(tmp / "link.ld"), str(tmp / "crt.S"), str(tmp / "t.c"), "-o", str(tmp / "t.elf")], capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr[:2000])
    subprocess.run([gcc[:-3] + "objcopy", "-O", "binary", str(tmp / "t.elf"), str(tmp / "t.bin")], check=True)
    b = (tmp / "t.bin").read_bytes()
    b += b"\0" * (-len(b) % 4)
    (tmp / "t.hex").write_text("\n".join("%08x" % struct.unpack("<I", b[i:i + 4])[0] for i in range(0, len(b), 4)) + "\n")
    out = vlsim.run(vlsim.build(net, HERE / "tests" / "gpu_tb.v"), [f"+HEX={tmp / 't.hex'}", f"+LIMIT={LIMIT}", "+LO=3fc000", "+HI=3fc00f"])
    if "--dump" in argv: print("\n".join(l for l in out.splitlines() if l.startswith(("W ", "TOHOST", "MIS", "BOTH", "BADFILL"))))
    m = re.search(r"TOHOST (\d+) (\d+)", out)
    val, cyc = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    if val == 1:
        print(f"PASS four harts drove four GPU cores at the same time ({', '.join(KERNELS)}); every result matched ({cyc} cycles)")
        sys.exit(0)
    if not val:
        print("FAIL no result within the cycle limit")
    else:
        code = (val - 1) // 2
        print(f"FAIL hart {code // 10000}: " + ("its core stopped with an error" if code % 10000 == 1 else f"result row {code % 10000 - 2} wrong"))
    sys.exit(1)
