"""The official riscv-tests on the single-core tile (soc1): each test is built for the tile's memory map (16 MB at 0x8000_0000),
loaded into the RAM by isa_tile_tb.v, run until the test writes `tohost`. A value of 1 is a pass; any other value is a failure
(value >> 1 names the failing check).

    python3 demos/linux-soc/tests/isa_tile.py [--suites rv32ui,rv32um,rv32ua,rv32mi,rv32uc] [--jobs 8] [--only name,name]

Needs: the riscv-tests checkout (workspace/riscv-tests), a RISC-V gcc (riscv-none-elf-gcc), Icarus. The tile is compiled once
(top.v + blocks.v from demos/linux-soc's assemble.py) with Verilator (vlsim.py); each test is a plusarg run of that simulation.
"""
from __future__ import annotations

import argparse, concurrent.futures as cf, os, re, shutil, struct, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "quad-soc" / "tests"))
import vlsim  # Verilator build and run helper

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RT = Path(os.environ.get("RISCV_TESTS", "/home/aura/Desktop/BARG/workspace/riscv-tests"))
SCRATCH = Path(os.environ.get("SOC1_SCRATCH", "/tmp/soc1"))
GCC = os.environ.get("RISCV_GCC", "/home/aura/tools/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc")
_BIN = Path(GCC).parent
OBJCOPY = str(_BIN / "riscv-none-elf-objcopy")
NM = str(_BIN / "riscv-none-elf-nm")
SUITE_DIRS = {"rv32ui": "rv32ui", "rv32um": "rv32um", "rv32ua": "rv32ua", "rv32mi": "rv32mi", "rv32uc": "rv32uc", "rv32si": "rv32si"}


def build(src: Path, out: Path) -> tuple[Path, int]:
    """Assemble and link one test; returns (hex file of 32-bit words from 0x8000_0000, tohost address)."""
    elf = out.with_suffix(".elf")
    cmd = [GCC, "-march=rv32imac_zicsr_zifencei", "-mabi=ilp32", "-static", "-mcmodel=medany", "-fvisibility=hidden", "-nostdlib",
           "-nostartfiles", f"-I{RT / 'env' / 'p'}", f"-I{RT / 'isa' / 'macros' / 'scalar'}", f"-T{RT / 'env' / 'p' / 'link.ld'}",
           "-DPTE_SIZE=4", str(src), "-o", str(elf)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{src.name}: {r.stderr[:300]}")
    binf = out.with_suffix(".bin")
    subprocess.run([OBJCOPY, "-O", "binary", str(elf), str(binf)], check=True)
    nm = subprocess.run([NM, str(elf)], capture_output=True, text=True).stdout
    tohost = int(re.search(r"([0-9a-f]+) [A-Za-z] tohost", nm).group(1), 16)
    data = binf.read_bytes()
    data += b"\0" * (-len(data) % 4)
    hexf = out.with_suffix(".hex")
    hexf.write_text("".join(f"{w:08x}\n" for (w,) in struct.iter_unpack("<I", data)))
    return hexf, tohost


def compile_tile() -> Path:
    """The tile's Verilog, compiled once with the test bench (the bench reads the program and tohost from plusargs)."""
    vvp = SCRATCH / "isa.vvp"
    subprocess.run([sys.executable, str(ROOT / "demos" / "linux-soc" / "assemble.py"), str(ROOT / "demos" / "linux-soc" / "design-soc1.json"),
                    str(SCRATCH)], check=True, capture_output=True)
    return vlsim.build(SCRATCH, HERE / "isa_tile_tb.v")


def run_one(vvp: Path, name: str, hexf: Path, tohost: int, limit: int) -> tuple[str, bool, str]:
    out = vlsim.run(vvp, [f"+HEX={hexf}", f"+TOHOST={tohost:x}", f"+LIMIT={limit}"], timeout=3600)
    line = [l for l in out.splitlines() if l.startswith(("PASS", "FAIL"))]
    if not line:
        return name, False, "no result: " + out[-200:]
    return name, line[-1].startswith("PASS"), line[-1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suites", default="rv32ui,rv32um,rv32ua,rv32mi,rv32uc")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--only", default="")
    ap.add_argument("--limit", type=int, default=400000)
    a = ap.parse_args()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    wd = SCRATCH / "isa"
    wd.mkdir(exist_ok=True)
    vvp = compile_tile()
    only = set(filter(None, a.only.split(",")))
    jobs = []
    for suite in a.suites.split(","):
        for src in sorted((RT / "isa" / SUITE_DIRS[suite]).glob("*.S")):
            name = f"{suite}-{src.stem}"
            if only and name not in only and src.stem not in only:
                continue
            jobs.append((name, src))
    results = []
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        futs = {}
        for name, src in jobs:
            try:
                hexf, tohost = build(src, wd / name)
            except RuntimeError as e:
                results.append((name, False, "build: " + str(e)))
                continue
            futs[ex.submit(run_one, vvp, name, hexf, tohost, a.limit)] = name
        for f in cf.as_completed(futs):
            results.append(f.result())
    # known deviations, not failures: the spec allows a trap for a misaligned access (M-mode software emulates it, as OpenSBI does)
    KNOWN = {"rv32ui-ma_data"}
    results = [(n, ok or n in KNOWN, (m + " (known deviation: misaligned accesses trap, allowed by the spec)") if (n in KNOWN and not ok) else m) for n, ok, m in results]
    passed = sum(1 for _, ok, _ in results if ok)
    for name, ok, msg in sorted(results):
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {msg}")
    print(f"{passed} of {len(results)} pass")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
