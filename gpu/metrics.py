"""Measured numbers for the GPU: each kernel on the assembled RTL (cycles from the Icarus run) with the instruction counts from the
model, then throughput per cycle.

    python3 demos/simt-gpu/metrics.py [--mhz 50]

Cycles are measured on the RTL. Work counts come from the kernels' sizes. The clock is an assumption (no timing closure yet), so
the per-second figures only scale the per-cycle ones.
"""

from __future__ import annotations

import argparse
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "model"))
import run_kernel  # noqa: E402
import run_rtl  # noqa: E402
import simt  # noqa: E402

LANES, WARPS = 4, 4
# (what one run computes, count) per kernel, from sizes in run_kernel.CASES
WORK = {"vecadd": ("int32 adds", 37), "reduce": ("int32 elements summed", 203), "gemm_i8": ("INT8 MACs", 16 * 16 * 16),
        "gemm_shared": ("INT8 MACs", 16 * 16 * 16), "conv2d": ("int32 MACs", 10 * 10 * 9), "collatz": ("sequences", 23)}


def model_stats(name: str) -> simt.Stats:
    with tempfile.TemporaryDirectory() as tmp:
        elf = run_kernel.compile_kernel(name, Path(tmp))
        gpu = simt.Gpu(simt.Config())
        syms = run_kernel.load_elf(gpu, elf)
        inputs, _ = run_kernel.CASES[name](random.Random(1))
        for sym, raw in inputs.items():
            gpu.write(syms[sym][0], raw + bytes(-len(raw) % 4))
        gpu.launch(syms["_start"][0])
        return gpu.run()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mhz", type=float, default=50.0)
    args = ap.parse_args()
    print(f"| kernel | cycles (RTL) | warp instr | thread instr | IPC (warp) | lane use | divergent splits | work | work/cycle | at {args.mhz:g} MHz |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    tot_c = tot_w = tot_t = 0
    for name in run_kernel.CASES:
        r = run_rtl.run_on_rtl(name)
        s = model_stats(name)
        cyc, wi, ti = r["cycles"], s.steps, s.thread_instructions
        what, n = WORK[name]
        per_s = n / cyc * args.mhz * 1e6
        print(f"| {name} | {cyc} | {wi} | {ti} | {wi / cyc:.3f} | {ti / (wi * LANES):.0%} | {s.divergent_splits} | {n} {what} | "
              f"{n / cyc:.4f} | {per_s / 1e6:.2f} M/s |")
        tot_c, tot_w, tot_t = tot_c + cyc, tot_w + wi, tot_t + ti
    print(f"\nall six: {tot_c} cycles, {tot_w} warp instructions, IPC {tot_w / tot_c:.3f}, "
          f"thread-instructions per cycle {tot_t / tot_c:.2f} of {LANES} peak per warp slot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
