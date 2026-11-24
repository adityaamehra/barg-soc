"""Check one RTL file against a block's golden model, directly with the harness (no backend, no model call).

    python3 demos/simt-gpu/check_rtl.py <block> [rtl-file] [-n examples]

The spec (ports, reset, latency) comes from design.json; the golden model and its directed `vectors` / `traces` from golden/.
With no RTL file it checks rtl/<block>.v. Exits 0 when the RTL agrees on every checked input.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
PYTHON = ROOT / ".venv-harness" / "bin" / "python"
HARNESS = ROOT / "packages" / "harness" / "src"


def spec_of(block: dict) -> dict:
    return {"moduleName": block["moduleName"], "resetStyle": block["resetStyle"], "latencyCycles": block["latencyCycles"],
            "encodings": [], "ports": [{"name": p["name"], "width": p["width"], "direction": p["direction"],
                                        **({"role": p["role"]} if "role" in p else {})} for p in block["ports"]]}


def check(block_name: str, rtl: Path, examples: int = 3, pool: int = 4000, home: Path = HERE) -> dict:
    """`home` holds design.json and golden/: this folder for the core, wishbone/ for the bridge."""
    design = json.loads((home / "design.json").read_text(encoding="utf-8"))
    block = next(b for b in design["blocks"] if b["name"] == block_name)
    clocked = any(p.get("role") == "clock" for p in block["ports"])
    with tempfile.TemporaryDirectory() as tmp:
        spec = Path(tmp) / "spec.json"
        spec.write_text(json.dumps(spec_of(block)))
        cmd = [str(PYTHON), "-m", "harness.cli", "golden-check", "--spec", str(spec), "--rtl", str(rtl),
               "--golden", str(home / "golden" / f"{block_name}.py"), "--function", f"golden_{block_name}",
               "--pool", str(pool)] + (["--stateful"] if clocked else [])
        run = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env={"PYTHONPATH": str(HARNESS), "PATH": "/usr/bin:/bin:/opt/homebrew/bin"})
    try:
        out = json.loads(run.stdout)
    except json.JSONDecodeError:
        return {"ran": False, "detail": (run.stdout + run.stderr)[-600:]}
    out["examples"] = (out.get("rtl") or {}).get("examples", [])[:examples]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("block")
    ap.add_argument("rtl", nargs="?")
    ap.add_argument("-n", type=int, default=3)
    args = ap.parse_args()
    rtl = Path(args.rtl) if args.rtl else HERE / "rtl" / f"{args.block}.v"
    out = check(args.block, rtl, args.n)
    if not out.get("ran"):
        print(f"{args.block}: could not run: {out.get('detail')}")
        return 2
    rtl_side = out.get("rtl") or {}
    ok = rtl_side.get("correct") is True
    print(f"{args.block}: {'AGREES' if ok else 'DIFFERS'} ({out.get('detail', '')[:120]}; mismatching {rtl_side.get('mismatching')})")
    fmt = lambda x: hex(x) if isinstance(x, int) and x > 9 else x  # noqa: E731
    for e in out["examples"]:
        print("  cycle", e.get("cycle"), "vector", {k: fmt(v) for k, v in e["vector"].items() if v not in (0,)} )
        for k, d in list(e["differs"].items())[:6]:
            print(f"      {k}: golden {fmt(d['golden'])}  actual {fmt(d['actual'])}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
