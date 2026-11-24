"""Run one of the NuttX SoC's checks (isa_tests, c_tests, soc_tests, nuttx_boot) on a design that places IPs.

    python3 demos/quad-soc/stage.py <flat dir> <script> [its arguments]
    e.g.  stage.py /tmp/flat isa_tests --design /tmp/flat/design.json --base 0x80000000

<flat dir> comes from `node packages/backend/dist/cli/ip.js flatten --workspace workspace --design <design.json> --out <flat dir>`:
a block that came from an IP takes the Verilog the IP library stored (<flat>/sources/<module>.v); any other block takes its best
finished job of the stage-4 SoC (gpu_bench._newest), or, for a block of a design of its own, `EXTRA_RTL=<dir>` (<dir>/<module>.v).
"""

from __future__ import annotations

import importlib.machinery
import os
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "gpu-soc"))
import gpu_bench  # noqa: E402  (loads soc_bench as module "soc_bench")

flat = Path(sys.argv[1])
extra = Path(os.environ["EXTRA_RTL"]) if os.environ.get("EXTRA_RTL") else None


def latest_delivered(workspace, design):
    out = {}
    for blk in design["blocks"]:
        mod = blk["moduleName"]
        if (flat / "sources" / f"{mod}.v").exists():
            out[blk["name"]] = (flat / "sources" / f"{mod}.v").read_text(encoding="utf-8")
        elif extra is not None and (extra / f"{mod}.v").exists():
            out[blk["name"]] = (extra / f"{mod}.v").read_text(encoding="utf-8")
        else:
            f = gpu_bench._newest("nuttx-soc-imac-16mb", blk["id"])
            if f is None:
                raise SystemExit(f"no Verilog for {blk['name']}")
            out[blk["name"]] = f.read_text(encoding="utf-8")
    return out


gpu_bench.sb.base.latest_delivered = latest_delivered
_orig_exec = importlib.machinery.SourceFileLoader.exec_module


def _exec(self, module):
    _orig_exec(self, module)
    if self.name == "rv32i_run_rtl":
        module.latest_delivered = latest_delivered


importlib.machinery.SourceFileLoader.exec_module = _exec
script = gpu_bench.SOC_DIR / f"{sys.argv[2]}.py"
sys.argv = [str(script), *sys.argv[3:]]
sys.path.insert(0, str(gpu_bench.SOC_DIR))
runpy.run_path(str(script), run_name="__main__")
