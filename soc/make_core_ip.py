"""Step 1 of the quad-core SoC: the stage-4 CPU core as an IP, the single-core SoC rebuilt from it.

    python3 demos/quad-soc/make_core_ip.py [--workspace workspace]

`rv_core` = every block of the stage-4 SoC (demos/nuttx-soc/design-a-16mb.json, 70 blocks) that is not shared: the pipeline, its
CSRs, multiply/divide, atomics, the instruction memories and the fetch path. The shared side stays outside: the RAM banks, the
region decoder, the bus strobes, the device read mux, CLINT, PLIC, UART. Nothing is generated: every block's Verilog is one BARG
already generated and accepted (demos/gpu-soc/make_ips.py's soc_entry).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "demos" / "gpu-soc"))
import make_ips  # noqa: E402

SHARED = {"dmem", "dmem1", "dmem2", "dmem3", "ram_bank_we", "ram_rdata_mux", "clint", "plic_regs", "plic_gateway", "plic_logic",
          "uart16550", "clint_decode", "plic_decode", "region_decode", "bus_ctl", "io_mux"}
OUT = HERE / "ip"


def main() -> None:
    ws = sys.argv[sys.argv.index("--workspace") + 1] if "--workspace" in sys.argv else str(ROOT / "workspace")
    OUT.mkdir(exist_ok=True)
    stage4 = json.loads(make_ips.gpu_bench.STAGE4.read_text())
    core = [b for b in stage4["blocks"] if b["name"] not in SHARED]
    (OUT / "core-blocks.txt").write_text("\n".join(b["id"] for b in core))
    (OUT / "map-core.json").write_text(json.dumps({b["name"]: make_ips.soc_entry(stage4["id"], b["id"]) for b in core}, indent=1))
    print(f"{len(core)} core blocks, {len(stage4['blocks']) - len(core)} shared")
    make_ips.ip("create", "--workspace", ws, "--design", str(make_ips.gpu_bench.STAGE4), "--name", "rv_core",
                "--note", "RV32IMAC pipelined core (stage 4 of the NuttX SoC): pipeline, CSRs, mul/div, atomics, fetch with C extension",
                "--sources", str(OUT / "map-core.json"), "--blocks", f"@{OUT / 'core-blocks.txt'}",
                "--collapse-out", str(HERE / "design-single.json"))


if __name__ == "__main__":
    main()
