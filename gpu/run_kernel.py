"""Compile a kernel (sw/kernels/<name>.c) with riscv64-elf-gcc, run it on the GPU model, and check it against a Python
reference that shares no code with the model.

    python3 demos/simt-gpu/run_kernel.py               # every kernel
    python3 demos/simt-gpu/run_kernel.py gemm_i8 -v    # one, with the model's statistics

Inputs and outputs are the kernel's global arrays, found by symbol name (nm) and written or read by the host, as a driver
copies buffers to and from a GPU.
"""

from __future__ import annotations

import argparse
import random
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE / "model"))
import simt  # noqa: E402

GCC = (shutil.which("riscv64-elf-gcc") or shutil.which("riscv64-unknown-elf-gcc") or shutil.which("riscv-none-elf-gcc")
       or next((str(p) for p in sorted(Path.home().glob("tools/xpack-riscv-none-elf-gcc-*/bin/riscv-none-elf-gcc"))), None))
CFLAGS = ["-march=rv32im_zicsr", "-mabi=ilp32", "-O2", "-ffreestanding", "-nostdlib", "-nostartfiles", "-static",
          "-mcmodel=medany", "-msmall-data-limit=0", "-fno-builtin", "-Wall", "-Wno-shadow"]


def compile_kernel(name: str, out: Path) -> Path:
    elf = out / f"{name}.elf"
    subprocess.run([GCC, *CFLAGS, "-T", str(HERE / "sw" / "link.ld"), str(HERE / "sw" / "crt0.S"),
                    str(HERE / "sw" / "kernels" / f"{name}.c"), "-o", str(elf)], check=True)
    return elf


def load_elf(gpu: simt.Gpu, elf: Path) -> dict[str, tuple[int, int]]:
    """Load every PT_LOAD segment; return the symbol table (name -> (address, size))."""
    raw = elf.read_bytes()
    assert raw[:4] == b"\x7fELF" and raw[4] == 1, "not a 32-bit ELF"
    phoff, = struct.unpack_from("<I", raw, 0x1C)
    phentsize, phnum = struct.unpack_from("<HH", raw, 0x2A)
    for i in range(phnum):
        p_type, off, _vaddr, paddr, filesz, memsz, _flags, _align = struct.unpack_from("<8I", raw, phoff + i * phentsize)
        if p_type == 1 and memsz:
            image = raw[off: off + filesz] + bytes(memsz - filesz)
            gpu.write(paddr, image)
    nm = subprocess.run([GCC[:-3] + "nm", "-S", str(elf)], check=True, capture_output=True, text=True).stdout
    syms = {}
    for line in nm.splitlines():
        parts = line.split()
        if len(parts) == 4:                       # address size type name
            syms[parts[3]] = (int(parts[0], 16), int(parts[1], 16))
        elif len(parts) == 3:                     # an assembly label has no size
            syms[parts[2]] = (int(parts[0], 16), 0)
    return syms


def words(values, signed=True) -> bytes:
    return b"".join(struct.pack("<i" if signed else "<I", v) for v in values)


def s32(v: int) -> int:
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v >> 31 else v


# --------------------------------------------------------------------------- #
# Kernels: (inputs to write, outputs to read and check)
# --------------------------------------------------------------------------- #

def case_vecadd(rnd):
    n = 37
    a = [rnd.randint(-10**6, 10**6) for _ in range(n)]
    b = [rnd.randint(-10**6, 10**6) for _ in range(n)]
    return {"n": words([n]), "a": words(a), "b": words(b)}, {"c": [x + y for x, y in zip(a, b)]}


def case_reduce(rnd):
    n = 203
    x = [rnd.randint(-1000, 1000) for _ in range(n)]
    return {"n": words([n]), "x": words(x)}, {"total": [sum(x)]}


def case_gemm_i8(rnd):
    N = 16
    A = [[rnd.randint(-128, 127) for _ in range(N)] for _ in range(N)]
    B = [[rnd.randint(-128, 127) for _ in range(N)] for _ in range(N)]
    flat = lambda m: bytes(v & 0xFF for row in m for v in row)
    bt = [[B[k][j] for k in range(N)] for j in range(N)]
    C = [sum(A[i][k] * B[k][j] for k in range(N)) for i in range(N) for j in range(N)]
    return {"a": flat(A), "bt": flat(bt)}, {"c": C}


def case_collatz(rnd):
    n = 23
    start = [rnd.randint(1, 300) for _ in range(n)]

    def steps(v):
        s = 0
        while v != 1:
            v = 3 * v + 1 if v & 1 else v >> 1
            s += 1
        return s
    return {"n": words([n]), "start": words(start, signed=False)}, {"steps": [steps(v) for v in start]}


def case_gemm_shared(rnd):
    return case_gemm_i8(rnd)


def case_conv2d(rnd):
    H = W = 12
    img = [[rnd.randint(-500, 500) for _ in range(W)] for _ in range(H)]
    k = [[rnd.randint(-9, 9) for _ in range(3)] for _ in range(3)]
    out = [sum(img[y + dy][x + dx] * k[dy][dx] for dy in range(3) for dx in range(3)) for y in range(H - 2) for x in range(W - 2)]
    return {"img": words(v for row in img for v in row), "k": words(v for row in k for v in row)}, {"out": out}


CASES = {"vecadd": case_vecadd, "reduce": case_reduce, "gemm_i8": case_gemm_i8, "collatz": case_collatz,
         "gemm_shared": case_gemm_shared, "conv2d": case_conv2d}


def run(name: str, seed: int = 1, verbose: bool = False, config: simt.Config | None = None) -> simt.Stats:
    with tempfile.TemporaryDirectory() as tmp:
        elf = compile_kernel(name, Path(tmp))
        gpu = simt.Gpu(config or simt.Config())
        syms = load_elf(gpu, elf)
        inputs, expected = CASES[name](random.Random(seed))
        for sym, raw in inputs.items():
            addr, size = syms[sym]
            assert len(raw) <= size, f"{sym}: {len(raw)} bytes for a {size}-byte symbol"
            gpu.write(addr, raw)
        gpu.launch(syms["_start"][0])
        stats = gpu.run()
        for sym, want in expected.items():
            addr, _ = syms[sym]
            got = [s32(v) for v in gpu.read_words(addr, len(want))]
            if got != [s32(v) for v in want]:
                bad = next(i for i, (g, w) in enumerate(zip(got, want)) if g != s32(w))
                raise AssertionError(f"{name}: {sym}[{bad}] = {got[bad]}, expected {s32(want[bad])}")
        if verbose:
            print(f"  {stats}")
        return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kernels", nargs="*", default=list(CASES))
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    if GCC is None:
        print("riscv64-elf-gcc not found")
        return 2
    for name in args.kernels:
        st = run(name, verbose=args.verbose)
        print(f"{name}: OK ({st.steps} warp instructions, {st.thread_instructions} thread instructions, "
              f"SIMT efficiency {st.thread_instructions / (4 * st.steps):.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
