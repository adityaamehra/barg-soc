"""Yosys synthesis of every block of the GPU to generic gates, with an area estimate for sky130 (sky130_fd_sc_hd).

    python3 demos/simt-gpu/synth_stats.py [--json out.json]

This is a first number, not signoff: no liberty file or place-and-route, so the area is the gate count times the typical cell area of
the sky130 high-density library, and a real mapper (which uses complex cells) usually lands 20 to 40 per cent lower. Memories
that are flip-flop arrays here (the register files) are counted as such; the SRAM banks are not synthesised (they become
OpenRAM macros) and are listed by size. Needs yosys.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
RTL = HERE / "rtl"
# sky130_fd_sc_hd typical cell areas in um^2 (nand2_1, inv_1, and2_1, or2_1, xor2_1, mux2_1, dfxtp_1, and2b_1, or2b_1)
AREA = {"$_NOT_": 3.75, "$_NAND_": 3.75, "$_NOR_": 3.75, "$_AND_": 6.26, "$_OR_": 6.26, "$_XOR_": 8.76, "$_XNOR_": 8.76,
        "$_MUX_": 11.26, "$_ANDNOT_": 7.51, "$_ORNOT_": 7.51, "$_DFF_P_": 20.02, "$_DFFE_PP_": 30.03, "$_DFF_PP0_": 25.02,
        "$_DFF_PN0_": 25.02, "$_SDFF_PP0_": 25.02, "$_SDFFE_PP0P_": 30.03, "$_DFFE_PP0P_": 30.03, "$_SDFFCE_PP0P_": 30.03}
MACROS = ("gbank", "sbank", "imem")          # SRAM: OpenRAM macros, not synthesised here


def synth(name: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        script = f"read_verilog -sv {RTL / (name + '.v')}; synth -top {name} -flatten; abc -g AND,NAND,OR,NOR,XOR,XNOR,ANDNOT,ORNOT,MUX; opt_clean -purge; stat"
        r = subprocess.run(["yosys", "-q", "-p", script, "-p", "tee -o /dev/stdout stat"], capture_output=True, text=True, cwd=tmp)
    out = r.stdout + r.stderr
    cells: dict[str, int] = {}
    for m in re.finditer(r"^\s+(\d+)\s+(?:[\d.]+\s+)?(\$_\w+_)\s*$", out, re.M):
        cells[m.group(2)] = int(m.group(1))
    if not cells:
        for m in re.finditer(r"^\s+(\$_\w+_)\s+(\d+)\s*$", out, re.M):
            cells[m.group(1)] = int(m.group(2))
    return cells


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    args = ap.parse_args()
    if not shutil.which("yosys"):
        print("needs yosys")
        return 1
    rows = []
    for f in sorted(RTL.glob("*.v")):
        name = f.stem
        if name == "top":
            continue
        if name.startswith(MACROS):
            rows.append({"block": name, "macro": True})
            continue
        cells = synth(name)
        gates = sum(n for c, n in cells.items() if "DFF" not in c)
        flops = sum(n for c, n in cells.items() if "DFF" in c)
        area = sum(AREA.get(c, 8.0) * n for c, n in cells.items())
        rows.append({"block": name, "gates": gates, "flops": flops, "area_um2": round(area), "cells": cells})
    print(f"{'block':<14}{'gates':>9}{'flops':>9}{'area um2':>11}")
    for r in rows:
        print(f"{r['block']:<14}" + ("   (SRAM macro)" if r.get("macro") else f"{r['gates']:>9}{r['flops']:>9}{r['area_um2']:>11}"))
    logic = [r for r in rows if not r.get("macro")]
    rf = [r for r in logic if r["block"].startswith("regfile")]
    rest = [r for r in logic if not r["block"].startswith("regfile")]
    print(f"\nlogic without register files: {sum(r['gates'] for r in rest)} gates, {sum(r['flops'] for r in rest)} flops, "
          f"{sum(r['area_um2'] for r in rest) / 1e6:.3f} mm2")
    print(f"register files as flip-flops (4 x 128 x 32): {sum(r['gates'] for r in rf)} gates, {sum(r['flops'] for r in rf)} flops, "
          f"{sum(r['area_um2'] for r in rf) / 1e6:.3f} mm2")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
