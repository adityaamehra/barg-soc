"""Yosys synthesis of the whole core (rtl/top.v and every block, flattened) to generic gates, with the SRAM banks and the instruction
memory left as black boxes (they become OpenRAM macros), and the longest combinational path in gate levels.

    python3 demos/simt-gpu/synth_top.py [--json out.json] [--rss-mb 3500]

The run is under a memory watchdog (fuzz_rtl.run_limited): Yosys is killed if it passes --rss-mb. Area uses the same typical
sky130_fd_sc_hd cell areas as synth_stats.py (no liberty file, no placement: +-30%). Needs yosys.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from fuzz_rtl import run_limited  # noqa: E402
from synth_stats import AREA, MACROS  # noqa: E402

RTL = HERE / "rtl"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--rss-mb", type=int, default=3500)
    args = ap.parse_args()
    if not shutil.which("yosys"):
        print("needs yosys")
        return 1
    files = sorted(RTL.glob("*.v"))
    macros = [p.stem for p in files if p.stem.startswith(MACROS)]
    script = "\n".join([
        *[f"read_verilog -sv {p}" for p in files],
        *[f"blackbox {m}" for m in macros],
        "hierarchy -top top", "synth -top top -flatten",
        "abc -g AND,NAND,OR,NOR,XOR,XNOR,ANDNOT,ORNOT,MUX", "opt_clean -purge", "tee -o stat.txt stat", "tee -o ltp.txt ltp -noff",
    ])
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "synth.ys").write_text(script + "\n")
        out = run_limited(["yosys", "-q", "-s", "synth.ys"], tmp, max_rss_mb=args.rss_mb, max_seconds=3600, max_out_mb=64)
        if out is None or not (tmp / "stat.txt").exists():
            print("Yosys was stopped or failed:", (out or "")[-500:])
            return 2
        stat = (tmp / "stat.txt").read_text()
        ltp = (tmp / "ltp.txt").read_text() if (tmp / "ltp.txt").exists() else ""
    cells = {m.group(2): int(m.group(1)) for m in re.finditer(r"^\s+(\d+)\s+(?:[\d.]+\s+)?(\$_\w+_)\s*$", stat, re.M)}
    if not cells:
        cells = {m.group(1): int(m.group(2)) for m in re.finditer(r"^\s+(\$_\w+_)\s+(\d+)\s*$", stat, re.M)}
    flops = sum(n for c, n in cells.items() if "DFF" in c)
    gates = sum(n for c, n in cells.items() if "DFF" not in c)
    area = sum(AREA.get(c, 8.0) * n for c, n in cells.items())
    depth = re.search(r"length=(\d+)", ltp)
    print(f"whole core, SRAM macros black-boxed: {gates} gates, {flops} flops, {area / 1e6:.3f} mm2 of cells")
    if depth:
        print(f"longest combinational path: {depth.group(1)} gate levels")
    print("cells:", dict(sorted(cells.items(), key=lambda kv: -kv[1])))
    if args.json:
        Path(args.json).write_text(json.dumps({"gates": gates, "flops": flops, "area_um2": round(area), "depth": int(depth.group(1)) if depth else None,
                                                "cells": cells}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
