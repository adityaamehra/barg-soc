"""Run one of the NuttX SoC's checks (isa_tests, c_tests, soc_tests, nuttx_boot) on the regenerated stage-4 SoC.

    python3 demos/gpu-soc/stage4.py <script> [its arguments]      e.g.  stage4.py isa_tests --design design-a-16mb.json --base 0x80000000

The stage-4 blocks were generated on two backends (workspace/ and workspace-mistral/) with several models; this picks each block's
best finished job across both (gpu_bench._newest: best verdict, then newest) instead of soc_bench's single workspace, then runs the
script unchanged.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import gpu_bench  # noqa: E402  (loads soc_bench as module "soc_bench")

sb = gpu_bench.sb


def latest_delivered(workspace, design):
    out = {}
    for blk in design["blocks"]:
        f = gpu_bench._newest(design["id"], blk["id"])
        if f is None:
            raise SystemExit(f"no finished job for {blk['name']}")
        out[blk["name"]] = f.read_text(encoding="utf-8")
    return out


sb.base.latest_delivered = latest_delivered
# the scripts load soc_bench afresh (and with it run_rtl), so patch every copy of run_rtl as it is loaded
_orig_exec = importlib.machinery.SourceFileLoader.exec_module


def _exec(self, module):
    _orig_exec(self, module)
    if self.name == "rv32i_run_rtl":
        module.latest_delivered = latest_delivered


importlib.machinery.SourceFileLoader.exec_module = _exec
script = gpu_bench.SOC_DIR / f"{sys.argv[1]}.py"
sys.argv = [str(script), *sys.argv[2:]]
sys.path.insert(0, str(gpu_bench.SOC_DIR))
runpy.run_path(str(script), run_name="__main__")
