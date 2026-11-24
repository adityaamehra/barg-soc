"""Bare-metal tests of the GPU cluster on the quad-core SoC's generated Verilog.

    python3 demos/gpu-cluster/cluster_tests.py <assembled netlist dir> [kernel ...] [--cores N] [--limit CYCLES]

Hart 0 (the others park) does what a driver does: it writes a compute kernel's code through the broadcast slot (core slot 15,
0x31E0_0000) so that all cores get the same, and each core's data to its own slot (a different random input per core with --distinct), starts every core with one broadcast CTRL write, polls each core's STATUS (core k is at
0x3000_0000 + k * 0x20_0000), then reads each core's results back (every GPU read twice: the bridge returns the previous GPU read) and
compares them with the kernel's reference from demos/simt-gpu/run_kernel.py. The image stores 1 to TOHOST (0x80FFF000) on a pass, or
failure code * 2 + 1.
"""
import random, re, struct, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "demos" / "gpu-soc"))
import gpu_tests as gt  # noqa: E402  (also puts demos/simt-gpu on the path)
import run_kernel  # noqa: E402
sys.path.insert(0, str(ROOT / "demos" / "quad-soc" / "tests"))
import vlsim  # noqa: E402
cp = gt.cp  # the module gpu_tests uses (ELF segment reader)

argv = sys.argv[1:]
args = [a for i, a in enumerate(argv) if not a.startswith("--") and not (i and argv[i - 1].startswith("--"))]
opt = lambda k, d: next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == f"--{k}"), d)  # noqa: E731
net = Path(args[0])
kernels = args[1:] or ["vecadd"]
N = int(opt("cores", 10))
LIMIT = int(opt("limit", 3000000))
BROADCAST = 0xF << 21
M = 0xFFFFFFFF
CRT = (".section .text.init\n.globl _start\n_start:\n  csrr t0, mhartid\n  bnez t0, 2f\n  li sp, 0x80F00000\n  call main\n"
       "1: j 1b\n2: j 2b\n")


def kernel_case(name, work):
    """Rows (slot, soc address, value): the code to the broadcast slot; each core's data to its own slot (a different random input per core
    with --distinct, else the same for all); its expected results as read rows (slot, address, value)."""
    import simt
    elf = run_kernel.compile_kernel(name, work)
    syms = run_kernel.load_elf(simt.Gpu(simt.Config()), elf)
    wr = []
    for a, seg in cp.elf_segments(elf):
        wr += [(15, gt.soc_addr(addr), v) for addr, v in gt.words(a, seg)]
    rd, sigs = [], set()
    for k in range(N):
        inputs, expected = run_kernel.CASES[name](random.Random(1 + (k if "--distinct" in sys.argv else 0)))
        wr += [(k, gt.soc_addr(addr), v) for sym, raw in inputs.items() for addr, v in gt.words(syms[sym][0], raw)]
        rd += [(k, gt.soc_addr(syms[sym][0] + 4 * i), v & M) for sym, want in expected.items() for i, v in enumerate(want)]
        sigs.add(tuple(v for _, _, v in rd[-sum(len(w) for w in expected.values()):]))
    if "--distinct" in sys.argv and len(sigs) != N:
        sys.exit(f"the {N} cores' expected results are not all different ({len(sigs)} distinct): the distinct-input check would be weaker")
    if "--corrupt" in sys.argv:  # negative control: one expected value is wrong, so the test must fail
        rd[0] = (rd[0][0], rd[0][1], rd[0][2] ^ 1)
    return wr, syms["_start"][0], rd


def source(writes, start, reads):
    def arr(name, rows):
        body = ",".join("{" + ",".join(f"0x{v & M:x}u" for v in r) + "}" for r in rows) or "{0}"
        return f"static const uint32_t {name}[][3] = {{{body}}};\n#define N_{name} {len(rows)}\n"
    return f"""#include <stdint.h>
#define REG(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define TOHOST REG({gt.TOHOST:#x})
#define SLOT(k) ((uint32_t)(k) << 21)
{arr("WR", writes)}{arr("RD", reads)}
static uint32_t rd(uint32_t a) {{ (void)REG(a); return REG(a); }}
static void fail(uint32_t code) {{ TOHOST = code * 2 + 1; for (;;) ; }}
int main(void) {{
    for (uint32_t i = 0; i < N_WR; i++) REG(WR[i][1] | SLOT(WR[i][0])) = WR[i][2];
    REG(0x30000000u | SLOT(15) | 4) = {start:#x}u;
    REG(0x30000000u | SLOT(15) | 8) = 0;
    REG(0x30000000u | SLOT(15)) = 1;
    for (uint32_t k = 0; k < {N}; k++) {{
        uint32_t st;
        do st = rd(0x3000000Cu | SLOT(k)); while (!(st & 6));
        if (st & 4) fail(1 + k);
    }}
    for (uint32_t i = 0; i < N_RD; i++) if (rd(RD[i][1] | SLOT(RD[i][0])) != RD[i][2]) fail(100 + i);
    TOHOST = 1;
    for (;;) ;
}}
"""


def build_image(src, tmp):
    (tmp / "t.c").write_text(src)
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
    return tmp / "t.hex"


ok = True
with tempfile.TemporaryDirectory() as t:
    tmp = Path(t)
    exe = vlsim.build(net, HERE / "tests" / "gpu_tb.v")
    for name in kernels:
        work = tmp / name
        work.mkdir()
        writes, start, reads = kernel_case(name, work)
        print(f"{name}: {len(writes)} words written, {len(reads)} result words checked over {N} cores" + (" (different input per core)" if "--distinct" in sys.argv else ""))
        hexf = build_image(source(writes, start, reads), work)
        out = vlsim.run(exe, [f"+HEX={hexf}", f"+LIMIT={LIMIT}"])
        m = re.search(r"TOHOST (\d+) (\d+)", out)
        val, cyc = (int(m.group(1)), int(m.group(2))) if m else (None, None)
        good = val == 1
        ok &= good
        why = "" if good else (" (no result: the program did not finish)" if val in (None, 0) else
                               f" (failure code {(val - 1) // 2}: " + ("a core stopped with an error)" if (val - 1) // 2 < 100 else
                                                                      f"result row {(val - 1) // 2 - 100}: core {reads[(val - 1) // 2 - 100][0]})"))
        print(("PASS " if good else "FAIL ") + f"{name} on {N} cores at once, results checked per core" + (", different input per core" if "--distinct" in sys.argv else "") + (f" ({cyc} cycles)" if good else why))
sys.exit(0 if ok else 1)
