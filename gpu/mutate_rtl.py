"""How good is the random-program fuzzer? Break the RTL one operator at a time and count the broken copies it notices.

    python3 demos/simt-gpu/mutate_rtl.py [--mutants 80] [--seed 1] [--programs 50] [--errors 50]

Each mutant is a copy of rtl/ with one operator or constant changed in one line of one logic block (the memories are skipped).
Some mutants change nothing observable (a dead branch, an out-of-range loop bound, a debug output), so the kill rate is a lower
bound on the fuzzer's strength. Runs two simulations at a time, each under the fuzzer's memory and time limits. Needs iverilog.
"""

from __future__ import annotations

import argparse
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
RTL = HERE / "rtl"
SKIP = {"top.v", "imem.v"} | {p.name for p in RTL.glob("*bank*.v")} | {p.name for p in RTL.glob("regfile*.v")}
SWAPS = [(r"\+", "-"), (r"==", "!="), (r"!=", "=="), (r" & ", " | "), (r" \| ", " & "), (r" \^ ", " | "), (r" < ", " <= "),
         (r" >= ", " > "), (r" > ", " >= "), (r"1'b1", "1'b0"), (r"1'b0", "1'b1"), (r"2'd1", "2'd2"), (r"2'd2", "2'd1"),
         (r"4'd1", "4'd2"), (r"3'd1", "3'd2"), (r"~", "")]


def sites():
    out = []
    for f in sorted(p for p in RTL.glob("*.v") if p.name not in SKIP):
        for i, line in enumerate(f.read_text().splitlines()):
            code = line.split("//")[0]
            if "=" not in code and "?" not in code:
                continue
            for pat, rep in SWAPS:
                out += [(f, i, m.start(), m.end(), rep) for m in re.finditer(pat, code)]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutants", type=int, default=80)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--programs", type=int, default=50)
    ap.add_argument("--errors", type=int, default=50)
    args = ap.parse_args()
    all_sites = sites()
    random.Random(args.seed).shuffle(all_sites)
    killed, survivors = 0, []
    for f, i, s, e, rep in all_sites[:args.mutants]:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            shutil.copytree(RTL, d / "rtl")
            lines = (d / "rtl" / f.name).read_text().splitlines()
            code, _, comment = lines[i].partition("//")
            mutated = code[:s] + rep + code[e:]
            lines[i] = mutated + (("//" + comment) if comment else "")
            (d / "rtl" / f.name).write_text("\n".join(lines) + "\n")
            try:
                r = subprocess.run([sys.executable, str(HERE / "fuzz_rtl.py"), "--programs", str(args.programs), "--errors",
                                    str(args.errors), "--jobs", "2"], env={**os.environ, "FUZZ_RTL": str(d / "rtl")},
                                   capture_output=True, text=True, timeout=600)
                dead = r.returncode != 0
            except subprocess.TimeoutExpired:
                dead = True
        if dead:
            killed += 1
        else:
            survivors.append(f"{f.name}:{i + 1}: {code.strip()}  ->  {mutated.strip()}")
    print(f"{killed} of {killed + len(survivors)} mutants noticed")
    print("\n".join(survivors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
