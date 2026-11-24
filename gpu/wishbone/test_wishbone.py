"""The Wishbone bridge: its block against the golden model, the six kernels through the Wishbone port (with and without random
gaps between transfers), the error path, and the window rules.

    ./.venv-harness/bin/python -m pytest demos/simt-gpu/wishbone -q
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "model"))
import check_rtl  # noqa: E402
import run_kernel  # noqa: E402
import run_wb  # noqa: E402
from asm import Asm  # noqa: E402

HAVE = shutil.which("iverilog") is not None and run_wb.BRIDGE.exists() and check_rtl.PYTHON.exists()
pytestmark = pytest.mark.skipif(not HAVE, reason="needs iverilog, the harness venv and wishbone/rtl/wb_bridge.v")

STATUS, ERR_PC, ERR_INFO = 0x3000000C, 0x30000010, 0x30000014


def test_the_bridge_agrees_with_its_golden_model():
    out = check_rtl.check("wb_bridge", run_wb.BRIDGE, home=HERE)
    assert out.get("ran"), out.get("detail")
    assert (out.get("rtl") or {}).get("correct") is True, out.get("examples")


@pytest.mark.skipif(run_kernel.GCC is None, reason="needs riscv64-elf-gcc")
@pytest.mark.parametrize("gaps", [False, True])
@pytest.mark.parametrize("kernel", list(run_kernel.CASES))
def test_kernel_through_the_wishbone_port(kernel, gaps):
    r = run_wb.run_on_wishbone(kernel, gaps=gaps)
    assert r["irq"].endswith("1"), f"user_irq[0] (done) should be high at the end, got {r['irq']}"


def test_an_illegal_instruction_stops_the_core_and_the_cause_is_readable():
    a = Asm()
    a.nop()
    a.raw(0)                                         # the all-zero word is illegal
    code = a.assemble()
    writes = [(run_wb.wb_address(4 * k), int.from_bytes(code[4 * k:4 * k + 4], "little")) for k in range(len(code) // 4)]
    out = run_wb.simulate(writes, [], 0)
    assert re.search(r"^ERROR 1 0$", out, re.M), out            # cause 1 (illegal), warp 0
    assert re.search(r"^ERRPC 4$", out, re.M), out


def test_partial_writes_misaligned_and_unmapped_accesses_are_dropped_and_acknowledged():
    # A program that ends at once (tmc 0), two good words in global memory, then four writes that must be dropped (a byte write, a
    # misaligned address, an unmapped window, an address outside the user window); every transfer is acknowledged (no HANG), the
    # good words are intact, and reads of unmapped or misaligned addresses answer 0.
    g = run_wb.wb_address(0x10000000)
    a = Asm()
    a.tmc("zero")
    word = int.from_bytes(a.assemble(), "little")
    writes = [(run_wb.wb_address(0), word), (g, 0x11223344), (g + 4, 0x55667788),
              (g, 0xAAAAAAAA), (g + 1, 0xBBBBBBBB), (0x30040000, 0xCCCCCCCC), (0x31020000 + 0, 0xDDDDDDDD)]
    sels = [15, 15, 15, 0b0001, 15, 15, 15]
    reads = [g, g + 4, g + 1, 0x30040000, 0x31020000, run_wb.wb_address(0x2000_0000)]
    out = run_wb.simulate(writes, reads, 0, sels=sels)
    assert "HANG" not in out and "DONE" in out, out
    got = {int(x): int(v) for x, v in re.findall(r"^R (\d+) (\d+)$", out, re.M)}
    assert got[g] == 0x11223344 and got[g + 4] == 0x55667788, got
    assert got[g + 1] == 0 and got[0x30040000] == 0 and got[0x31020000] == 0, got


def test_the_address_map():
    assert run_wb.wb_address(0x30000004) == 0x30000004
    assert run_wb.wb_address(0x00000010) == 0x30010010
    assert run_wb.wb_address(0x10000020) == 0x30020020
    assert run_wb.wb_address(0x20000FFC) == 0x30030FFC
