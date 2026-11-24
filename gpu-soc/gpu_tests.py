"""Stage G3 check: bare-metal programs on the GPU SoC's generated Verilog drive the GPU through gpu_bridge.

    python3 demos/gpu-soc/gpu_tests.py [test ...] [--fast]

Each test is a C program for the SoC's core (linked at 0x8000_0000) that does what a driver does, with word stores and loads only:
it writes a GPU kernel's code and data into the GPU's windows, sets START_PC and KARG, writes CTRL = 1, polls STATUS until done (or
error), and reads results back, every GPU address read twice (the bridge returns the previous GPU read). The values it compares with
are computed in Python beforehand: the compute kernels' references (demos/simt-gpu/run_kernel.py) and, for the graphics scenes, a
checksum of the frame model's pixels (demos/simt-gpu/gfx/scenes.py). The program stores 1 (pass) or an odd failure code to TOHOST.
Tests: the six compute kernels (vecadd ... conv2d) and the triangle kernel on the scenes tex_small and depth_small (rows 0..39).
"""

from __future__ import annotations

import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
GPU = ROOT / "demos" / "simt-gpu"
sys.path[:0] = [str(HERE), str(GPU), str(GPU / "model"), str(GPU / "gfx")]
import check_pipeline as cp  # noqa: E402
import run_kernel  # noqa: E402
import scenes  # noqa: E402
import run_g2a  # noqa: E402

os.environ.setdefault("VF_RISCV_GCC", run_kernel.GCC)
import gpu_bench  # noqa: E402

TOHOST = 0x80FF_F000
M = 0xFFFFFFFF
LINK = "ENTRY(_start)\nSECTIONS { . = 0x80000000; .text : { *(.text.init) *(.text*) *(.rodata*) } .data : { *(.data*) } .bss : { *(.bss*) } }\n"
CRT = ".section .text.init\n.globl _start\n_start:\n  li sp, 0x80F00000\n  call main\n1: j 1b\n"


def soc_addr(h: int) -> int:
    """The SoC address of a GPU host address (gpu_bridge's translation, inverted)."""
    if h >> 16 == 0x3000:
        return 0x3000_0000 | h & 0xFFFF
    if h < 0x800:
        return 0x3001_0000 | h
    if h >> 28 == 1:
        return 0x3002_0000 | h & 0x1FFF
    if h >> 28 == 2:
        return 0x3003_0000 | h & 0xFFF
    if 0x4004_0000 <= h < 0x4006_5800:
        return 0x3014_0000 | h - 0x4004_0000
    if 0x4000_0000 <= h < 0x4002_5800:
        return 0x3010_0000 | h & 0x3FFFF
    if h >> 28 == 5:
        return 0x3018_0000 | h & 0x7FF
    raise ValueError(hex(h))


def words(addr: int, raw: bytes):
    raw = raw + bytes(-len(raw) % 4)
    return [(addr + k, int.from_bytes(raw[k:k + 4], "little")) for k in range(0, len(raw), 4)]


def program(writes, start, reads=(), fills=(), sum_range=None, sum_want=0) -> str:
    """C source: fills (soc addr, count, value), writes (soc addr, value), start the GPU, poll, then reads (soc addr, expected) and a
    checksum s = s * 31 + word over sum_range (soc addr, words)."""
    def arr(name, rows):
        body = ",".join("{" + ",".join(f"0x{v & M:x}u" for v in r) + "}" for r in rows) or "{0}"
        return f"static const uint32_t {name}[][{len(rows[0]) if rows else 2}] = {{{body}}};\n#define N_{name} {len(rows)}\n"
    return f"""#include <stdint.h>
#define REG(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define TOHOST REG({TOHOST:#x})
{arr("FILLS", list(fills))}{arr("WR", list(writes))}{arr("RD", list(reads))}
static uint32_t rd(uint32_t a) {{ (void)REG(a); return REG(a); }}
static void fail(uint32_t code) {{ TOHOST = code * 2 + 1; for (;;) ; }}
int main(void) {{
    for (uint32_t f = 0; f < N_FILLS; f++)
        for (uint32_t k = 0; k < FILLS[f][1]; k++) REG(FILLS[f][0] + 4 * k) = FILLS[f][2];
    for (uint32_t i = 0; i < N_WR; i++) REG(WR[i][0]) = WR[i][1];
    REG(0x30000004) = {start:#x}u; REG(0x30000008) = 0; REG(0x30000000) = 1;
    uint32_t st;
    do st = rd(0x3000000C); while (!(st & 6));
    if (st & 4) fail(1);
    for (uint32_t i = 0; i < N_RD; i++) if (rd(RD[i][0]) != RD[i][1]) fail(i + 2);
    {"" if sum_range is None else f'''uint32_t s = 0;
    for (uint32_t k = 0; k < {sum_range[1]}u; k++) s = s * 31 + rd({sum_range[0]:#x}u + 4 * k);
    if (s != {sum_want & M:#x}u) fail(0x7FFF);'''}
    TOHOST = 1;
    for (;;) ;
}}
"""


def build(src: str, work: Path) -> bytes:
    gcc = run_kernel.GCC
    work.mkdir(parents=True, exist_ok=True)
    (work / "t.c").write_text(src)
    (work / "crt.S").write_text(CRT)
    (work / "link.ld").write_text(LINK)
    r = subprocess.run([gcc, "-march=rv32imac_zicsr", "-mabi=ilp32", "-O2", "-ffreestanding", "-nostdlib", "-nostartfiles", "-static",
                        "-T", str(work / "link.ld"), str(work / "crt.S"), str(work / "t.c"), "-o", str(work / "t.elf")],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr[:2000])
    subprocess.run([gcc[:-3] + "objcopy", "-O", "binary", str(work / "t.elf"), str(work / "t.bin")], check=True)
    return (work / "t.bin").read_bytes()


def compute_test(name: str, work: Path):
    import random
    work.mkdir(parents=True, exist_ok=True)
    elf = run_kernel.compile_kernel(name, work)
    import simt
    syms = run_kernel.load_elf(simt.Gpu(simt.Config()), elf)
    inputs, expected = run_kernel.CASES[name](random.Random(1))
    wr = [w for a, seg in cp.elf_segments(elf) for w in words(a, seg)]
    wr += [w for sym, raw in inputs.items() for w in words(syms[sym][0], raw)]
    rd = [(syms[sym][0] + 4 * k, v & M) for sym, want in expected.items() for k, v in enumerate(want)]
    return program([(soc_addr(a), v) for a, v in wr], syms["_start"][0], [(soc_addr(a), v) for a, v in rd])


def scene_test(scene: str, work: Path, rows: int = 40):
    elf = work / "tri_rast.elf"
    work.mkdir(parents=True, exist_ok=True)
    subprocess.run([run_kernel.GCC, *run_kernel.CFLAGS, "-T", str(GPU / "sw" / "link.ld"), str(GPU / "sw" / "crt0.S"),
                    str(GPU / "gfx" / "sw" / "tri_rast.c"), "-o", str(elf)], check=True)
    import simt
    syms = run_kernel.load_elf(simt.Gpu(simt.Config()), elf)
    clear, tris = scenes.scene(scene)
    tex, zclear = scenes.texture(scene), scenes.depth_clear(scene)
    want = scenes.frame(clear, tris, tex, zclear)
    data = run_g2a.scene_bytes(syms, clear, tris, tex, None)
    wr = [w for a, seg in cp.elf_segments(elf) for w in words(a, seg)]
    wr += [w for a, raw in data.items() for w in words(a, raw)]
    fills = [] if zclear is None else [(soc_addr(0x4004_0000), 320 * 240 // 2, zclear << 16 | zclear)]
    s = 0
    for p in range(0, rows * 320, 2):
        s = (s * 31 + (want[p + 1] << 16 | want[p])) & M
    return program([(soc_addr(a), v) for a, v in wr], syms["_start"][0], fills=fills, sum_range=(0x3010_0000, rows * 160), sum_want=s)


TESTS = {**{k: ("compute", k) for k in run_kernel.CASES}, "tex_small": ("scene", "tex_small"), "depth_small": ("scene", "depth_small")}


def main() -> int:
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or list(TESTS)
    fast = "--fast" in sys.argv
    soc = gpu_bench.soc()
    failed = 0
    try:
        for name in names:
            kind, arg = TESTS[name]
            work = soc.tmp / f"build-{name}"
            src = compute_test(arg, work) if kind == "compute" else scene_test(arg, work)
            image = build(src, work)
            r = soc.run(name, image, tohost=TOHOST, max_cycles=6_000_000 if kind == "scene" else 1_500_000, timeout=7200, fast=fast)
            ok = r["passed"]
            print(f"{'ok  ' if ok else 'FAIL'} {name}: {r['cycles']} cycles" + ("" if ok else f" ({r['detail'] or r['value']})"), flush=True)
            failed += not ok
    finally:
        soc.close()
    print("all GPU SoC tests pass" if not failed else f"{failed} test(s) failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
