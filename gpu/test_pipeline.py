"""The design (design.json) on a netlist of its golden models: the kernels give the model's results, and an error stops the
core with the right cause and pc (check_pipeline.py).

    ./.venv-harness/bin/python -m pytest demos/simt-gpu/test_pipeline.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "model"))
import check_pipeline as cp  # noqa: E402
import run_kernel  # noqa: E402
from asm import Asm  # noqa: E402


@pytest.mark.skipif(run_kernel.GCC is None, reason="needs riscv64-elf-gcc")
@pytest.mark.parametrize("name", list(run_kernel.CASES))
def test_kernel_on_the_netlist(name):
    r = cp.run_on_netlist(name)
    assert r["cycles"] >= r["steps"]                     # at most one warp instruction per cycle


def boot(program: Asm):
    net = cp.Netlist(json.loads((Path(__file__).parent / "design.json").read_text()))
    host = cp.Host(net)
    net.top["rst"] = 1
    host.idle(2)
    net.top["rst"] = 0
    host.write_bytes(0, program.assemble())
    host.write(0x3000_0004, 0)
    host.write(0x3000_0000, 1)
    for _ in range(2000):
        net.settle()
        if net.out("done") or net.out("error"):
            break
        host.idle()
    return net, host


@pytest.mark.parametrize("build,cause,pc", [
    (lambda a: (a.nop(), a.raw(0x00000073)), 1, 4),                      # ecall: illegal
    (lambda a: (a.li("t0", 0x1000_0002), a.lw("t1", 0, "t0")), 2, 8),     # misaligned load (li is 2 words here)
    (lambda a: a.join(), 3, 0),                                          # join with an empty stack
    (lambda a: a.mma("a0", "a1"), 4, 0),                                 # tensor instruction with one lane active
    (lambda a: a.csrr("t0", 0x123), 5, 0),                               # no such CSR
])
def test_errors_stop_the_core_with_their_cause_and_pc(build, cause, pc):
    a = Asm()
    build(a)
    net, host = boot(a)
    assert net.out("error") == 1 and net.out("done") == 0
    assert host.read(0x3000_0014) & 15 == cause
    assert host.read(0x3000_0010) == pc
    assert host.read(0x3000_000C) == 0b100                               # not running, not done, error


def test_a_kernel_that_ends_reports_done_and_its_stores_are_readable():
    a = Asm()
    a.li("t0", 0x1000_0040)
    a.li("t1", 1234)
    a.sw("t1", 0, "t0")
    a.tmc("zero")
    net, host = boot(a)
    assert net.out("done") == 1 and net.out("error") == 0
    assert host.read(0x1000_0040) == 1234
    assert host.read(0x3000_000C) == 0b010
