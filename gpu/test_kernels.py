"""The C kernels (sw/kernels) compiled with riscv64-elf-gcc and run on the model, each against its Python reference
(run_kernel.py). Skipped when the compiler is missing.

    ./.venv-harness/bin/python -m pytest demos/simt-gpu -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import run_kernel  # noqa: E402


@pytest.mark.skipif(run_kernel.GCC is None, reason="needs riscv64-elf-gcc")
@pytest.mark.parametrize("name", list(run_kernel.CASES))
@pytest.mark.parametrize("seed", [1, 2])
def test_kernel(name, seed):
    stats = run_kernel.run(name, seed=seed)
    assert stats.divergent_branches == 0


@pytest.mark.skipif(run_kernel.GCC is None, reason="needs riscv64-elf-gcc")
@pytest.mark.parametrize("name", list(run_kernel.CASES))
@pytest.mark.parametrize("policy", ["rr", "gto", "gty"])
def test_kernel_results_do_not_depend_on_the_scheduler_or_the_timing(name, policy):
    stats = run_kernel.run(name, seed=3, config=run_kernel.simt.Config(scheduler=policy, timing=run_kernel.simt.Timing()))
    assert stats.cycles >= stats.steps            # at most one warp instruction per cycle
