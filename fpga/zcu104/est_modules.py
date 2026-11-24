#!/usr/bin/env python3
"""Per-block FPGA resource estimate of the quad SoC with Yosys (synth_xilinx, UltraScale+), then summed over the instances of soc_core.
The whole design does not fit one Yosys run in 30 GB, so each distinct block module is synthesised on its own (with the modules it instantiates), and the totals are
count x module. Block memories with an `initial` zero loop are read from build/blocks_est.v (loop removed: Yosys unrolls it)."""
import json, re, subprocess, sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
B = Path(__file__).resolve().parent / "build"
src = (B / "blocks_est.v").read_text() + (B / "src/barg_uart.v").read_text() + (B / "src/barg_fifo.v").read_text()
text = {}
for p in re.split(r'(?m)^(?=module )', src):
    m = re.match(r'module\s+(\w+)', p)
    if m: text[m.group(1)] = p
inst = Counter(re.findall(r'(?m)^  (\w+)\s+u_\w+\s*\(', (B / "src/soc_core.v").read_text()))
inst = Counter({k: v for k, v in inst.items() if k in text})
def closure(n, seen=None):
    seen = seen if seen is not None else set()
    if n in seen: return seen
    seen.add(n)
    for w in re.findall(r'\b(\w+)\s+(?:#\([^;]*?\)\s*)?\w+\s*\(', text[n]):
        if w in text: closure(w, seen)
    return seen
(B / "m").mkdir(exist_ok=True)
def run(n):
    f = B / "m" / f"{n}.v"; f.write_text("".join(text[x] for x in sorted(closure(n))))
    ys = f"read_verilog -sv {f}\nhierarchy -top {n}\nsynth_xilinx -family xcup -top {n} -nodsp -noiopad\ntee -q -o {B}/m/{n}.json stat -json -top {n}\n"
    try:
        r = subprocess.run(["bash", "-c", f"ulimit -v 8000000; timeout 240 yosys -q -p '{ys}'"], capture_output=True, text=True)
    except Exception as e: return n, None
    try: return n, json.loads((B / "m" / f"{n}.json").read_text())["design"]["num_cells_by_type"]
    except Exception: return n, None
res = dict(ThreadPoolExecutor(6).map(run, sorted(inst)))
tot = Counter(); fail = []
for n, c in inst.items():
    if res.get(n) is None: fail.append(n); continue
    for k, v in res[n].items(): tot[k] += v * c
def s(pref): return sum(v for k, v in tot.items() if k.startswith(pref))
out = {"modules": len(inst), "instances": sum(inst.values()), "failed": fail, "LUT": s("LUT"), "FF": s("FD"), "CARRY8": tot["CARRY8"], "RAMB36": tot["RAMB36E2"], "RAMB18": tot["RAMB18E2"], "URAM": tot["URAM288"], "DSP": s("DSP"), "LUTRAM": s("RAM32") + s("RAM64"), "other": {k: v for k, v in tot.items() if not k.startswith(("LUT", "FD", "CARRY", "RAMB", "URAM", "DSP", "RAM32", "RAM64", "$"))}}
(B / "est_modules.json").write_text(json.dumps({"total": out, "per_module": {n: dict(res[n]) for n in res if res[n]}}, indent=1))
print(json.dumps(out))
