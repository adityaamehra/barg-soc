"""Estimated cycles of every kernel under the three warp schedulers and for 1, 2 and 4 warps (model/simt.py, Timing).

    python3 demos/simt-gpu/compare_schedulers.py

The functional results are checked in every configuration (run_kernel.run raises on a wrong answer); the cycle counts come
from the assumed latencies of simt.Timing, so they compare choices, they do not predict the chip.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import run_kernel  # noqa: E402
import simt  # noqa: E402


def main() -> int:
    rows = []
    for name in run_kernel.CASES:
        for warps in (1, 2, 4):
            for policy in ("rr", "gto", "gty"):
                st = run_kernel.run(name, config=simt.Config(warps=warps, scheduler=policy, timing=simt.Timing()))
                rows.append((name, warps, policy, st.cycles, st.idle_cycles, st.thread_instructions / st.cycles))
    print(f"{'kernel':10} {'warps':>5} {'sched':>5} {'cycles':>8} {'idle':>7} {'thread IPC':>10}")
    for name, warps, policy, cycles, idle, ipc in rows:
        print(f"{name:10} {warps:>5} {policy:>5} {cycles:>8} {idle:>7} {ipc:>10.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
