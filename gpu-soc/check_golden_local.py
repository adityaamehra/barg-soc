"""A block's RTL against its golden model (demos/gpu-soc/golden/<name>.py) under Icarus, without the backend.

    python3 demos/gpu-soc/check_golden_local.py <block> <file.v> [...]

The same evidence as the backend's golden check: a clocked golden (with `traces(rng)`) is run trace by trace, its outputs compared
before each rising edge; a combinational one (with `vectors(rng)`) vector by vector. Used by export_gfx.py when the backend's check
could not judge the RTL (it stops when the generator's own reference model does not run). Ports and widths come from design.json.
"""

from __future__ import annotations

import importlib
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent


def check(name: str, rtl: Path, seed: int = 11, golden_dir: Path | None = None, design_path: Path | None = None) -> tuple[int, int, str]:
    """(differing cycles or vectors, total, first difference)"""
    sys.path.insert(0, str(golden_dir or HERE / "golden"))
    gold = importlib.import_module(name)
    block = next(b for b in json.loads((design_path or HERE / "design.json").read_text())["blocks"] if b["name"] == name)
    ports = {p["name"]: (p["direction"], p["width"]) for p in block["ports"]}
    clocked = hasattr(gold, "traces")
    ins = [p for p, (d, _) in ports.items() if d == "in" and p != "clk"]
    outs = [p for p, (d, _) in ports.items() if d == "out"]
    if clocked:
        runs = gold.traces(random.Random(seed))
        steps = [s for t in runs for s in t]
        want = [o for t in runs for o in getattr(gold, f"golden_{name}")(t)]
    elif hasattr(gold, "vectors"):
        steps = gold.vectors(random.Random(seed))
    else:                                       # a combinational golden without directed vectors: random inputs
        rng = random.Random(seed)
        steps = [{p: rng.getrandbits(ports[p][1]) for p in ins} for _ in range(2000)]
    if not clocked:
        want = [getattr(gold, f"golden_{name}")(**v) for v in steps]
    decl = " ".join(f"reg [{ports[p][1] - 1}:0] {p};" for p in ins) + " " + " ".join(f"wire [{ports[p][1] - 1}:0] {p};" for p in outs)
    conn = ", ".join(f".{p}({p})" for p in ins + outs) + (", .clk(clk)" if "clk" in ports else "")
    tb = f"""module tb; reg clk = 0; {decl}
  {name} u({conn});
  integer f, o, n;
  initial begin f = $fopen("in.txt", "r"); o = $fopen("out.txt", "w");
    while (!$feof(f)) begin n = $fscanf(f, "{' '.join('%h' for _ in ins)}\\n", {', '.join(ins)});
      #1 $fdisplay(o, "{' '.join('%h' for _ in outs)}", {', '.join(outs)}); #4 clk = 1; #5 clk = 0; end
    $fclose(o); $finish; end
endmodule"""
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "tb.v").write_text(tb)
        (d / "in.txt").write_text("".join(" ".join(f"{s.get(p, 0):x}" for p in ins) + "\n" for s in steps))
        built = subprocess.run(["iverilog", "-g2012", "-o", str(d / "sim"), str(d / "tb.v"), str(rtl)], capture_output=True, text=True)
        if built.returncode:
            return len(want), len(want), "does not compile: " + built.stderr[:200]
        subprocess.run(["vvp", "-n", str(d / "sim")], cwd=d, check=True, capture_output=True)
        got = (d / "out.txt").read_text().split("\n")
    if want and isinstance(want[0], dict):
        missing = sorted(set(want[0]) - set(outs))
        if missing:                                 # a golden output the block lacks would pass vacuously: refuse
            return len(want), len(want), f"golden outputs not on the block: {missing}"
    bad, first = 0, ""
    for n, (line, w) in enumerate(zip(got, want)):
        for p, v in zip(outs, line.split()):
            if w.get(p) is None:
                continue
            if "x" in v.lower() or "z" in v.lower() or int(v, 16) != w[p]:
                bad += 1
                first = first or f"{'cycle' if clocked else 'vector'} {n}: {p} = {v}, golden {w[p]:x}"
                break
    return bad, len(want), first


if __name__ == "__main__":
    name = sys.argv[1]
    worst = 0
    for f in sys.argv[2:]:
        bad, total, first = check(name, Path(f))
        worst = max(worst, bad)
        print(f"{f}: {'agrees with the golden model on all' if not bad else f'differs on {bad} of'} {total}" + (f"; {first}" if first else ""))
    sys.exit(1 if worst else 0)
