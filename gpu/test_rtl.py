"""The final RTL (rtl/*.v): every block against its golden model under directed stimulus, and the six kernels on the whole
assembled design under Icarus.

    ./.venv-harness/bin/python -m pytest demos/simt-gpu/test_rtl.py -q
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "model"))
import check_rtl  # noqa: E402
import run_kernel  # noqa: E402
import fuzz_rtl  # noqa: E402
import run_rtl  # noqa: E402

HAVE = shutil.which("iverilog") is not None and (HERE / "rtl" / "top.v").exists() and (check_rtl.PYTHON).exists()
GOLDEN = sorted(p.stem for p in (HERE / "golden").glob("*.py"))


@pytest.mark.skipif(not HAVE, reason="needs iverilog, the harness venv and rtl/")
@pytest.mark.parametrize("block", GOLDEN)
def test_block_agrees_with_its_golden_model(block):
    out = check_rtl.check(block, HERE / "rtl" / f"{block}.v")
    assert out.get("ran"), out.get("detail")
    assert (out.get("rtl") or {}).get("correct") is True, f"{block}: {out.get('detail')} {out.get('examples')}"


@pytest.mark.skipif(not HAVE or run_kernel.GCC is None, reason="needs iverilog, riscv64-elf-gcc and rtl/")
@pytest.mark.parametrize("kernel", list(run_kernel.CASES))
def test_kernel_on_the_generated_rtl(kernel):
    r = run_rtl.run_on_rtl(kernel)
    assert r["cycles"] >= r["steps"]


@pytest.mark.skipif(not HAVE, reason="needs iverilog, the harness venv and rtl/")
@pytest.mark.parametrize("seed", range(1, 13))
def test_random_programs_run_alike_on_the_rtl_and_the_model(seed):
    """fuzz_rtl.py: random legal programs (divergence, loops, shuffles, tensor ops, barriers) and programs that end in a fault;
    memory, and for a fault the cause, warp and pc, must be identical."""
    for faulty in (False, True):
        r = fuzz_rtl.one((seed, faulty))
        assert r["status"] == "ok", r
