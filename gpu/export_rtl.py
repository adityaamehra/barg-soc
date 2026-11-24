"""Choose the best generated RTL for every block of the GPU design, copy it into demos/simt-gpu/rtl/, and emit the top level.

    python3 demos/simt-gpu/export_rtl.py [http://127.0.0.1:3001]

For each block, among its finished jobs on the backend: the newest whose RTL agrees with the block's golden model on every
checked input (the golden check, run here if it has not been), else the best verdict and fewest mismatches, else the newest.
The choice, with its evidence, is written to rtl/manifest.json; rtl/generated/<block>.v is BARG's delivered Verilog, untouched;
rtl/corrected/<block>.v (kept by hand) replaces it where one exists; rtl/<block>.v is what is used; rtl/top.v is the
structural top level the graph package emits from design.json (the design's own nets, nothing hand-wired).
A block that is only the newest, because no generation agrees with its golden model, is listed in the manifest as "unresolved".
"""

import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3001").rstrip("/")
DESIGN = "simt-gpu"
WORKSPACE = ROOT / "workspace" / DESIGN
RANK = {"VERIFIED": 0, "VERIFIED_LOWCONF": 1, "REVIEW": 2}


def get(path):
    try:
        return json.load(urllib.request.urlopen(BASE + path, timeout=60))
    except urllib.error.HTTPError:
        return None


def post(path):
    req = urllib.request.Request(BASE + path, method="POST", data=b"{}", headers={"content-type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError:
        pass


def mismatches(detail: str) -> int:
    m = re.search(r"RTL: differs from the golden model on (\d+) of", detail or "")
    return int(m.group(1)) if m else 0


def main() -> int:
    design = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
    jobs = [dict(j, order=n) for n, j in enumerate(get(f"/api/jobs?designId={DESIGN}")) if j["state"] == "done"]
    by_block: dict[str, list[dict]] = {}
    for j in jobs:
        by_block.setdefault(j["blockId"], []).append(j)
    for blk in design["blocks"]:
        for j in by_block.get(blk["id"], []):
            post(f"/api/jobs/{j['id']}/golden-check")
    deadline = time.time() + 900
    while time.time() < deadline:                  # the checks run in the background; wait until none is pending
        pending = [j for blk in design["blocks"] for j in by_block.get(blk["id"], [])
                   if (get(f"/api/jobs/{j['id']}/golden-check") or {}).get("status") == "pending"]
        if not pending:
            break
        time.sleep(10)
    out = HERE / "rtl"
    gen_dir, corrected_dir = out / "generated", out / "corrected"
    gen_dir.mkdir(parents=True, exist_ok=True)
    corrected_dir.mkdir(exist_ok=True)
    manifest, unresolved = {}, []
    for blk in design["blocks"]:
        candidates = []
        for j in by_block.get(blk["id"], []):
            reply = get(f"/api/jobs/{j['id']}/golden-check") or {}
            res = reply.get("result") or {}
            status = reply.get("status", "no_golden")
            agrees = res.get("rtlCorrect") is True
            candidates.append({"job": j["id"], "verdict": j.get("verdict"), "golden": status, "agrees": agrees,
                               "mismatches": mismatches(res.get("detail", "")) if status == "checked" and not agrees else 0,
                               "detail": (res.get("detail") or "")[:140], "created": j["order"]})
        if not candidates:
            raise SystemExit(f"no finished job for {blk['name']}")
        has_golden = any(c["golden"] == "checked" for c in candidates)

        newest_first = sorted(candidates, key=lambda c: c["created"], reverse=True)
        # a stable sort keeps the newest first among equals: agreement, then fewest mismatches, then the better verdict
        best = sorted(newest_first, key=lambda c: (0 if (c["agrees"] or c["golden"] == "no_golden") else 1,
                                                   c["mismatches"], RANK.get(c["verdict"], 3)))[0]
        if has_golden and not best["agrees"]:
            unresolved.append(blk["name"])
        generated = (WORKSPACE / "jobs" / best["job"] / "delivered.v").read_text(encoding="utf-8")
        (gen_dir / f"{blk['name']}.v").write_text(generated, encoding="utf-8")        # BARG's output, untouched
        fixed = corrected_dir / f"{blk['name']}.v"
        (out / f"{blk['name']}.v").write_text(fixed.read_text(encoding="utf-8") if fixed.exists() else generated,
                                              encoding="utf-8")
        manifest[blk["name"]] = {"chosen": best["job"], "verdict": best["verdict"], "golden": best["golden"],
                                 "agrees_with_golden": best["agrees"], "detail": best["detail"],
                                 "generations": len(candidates), "hand_corrected": fixed.exists()}
    (out / "manifest.json").write_text(json.dumps({"unresolved": unresolved, "blocks": manifest}, indent=2) + "\n",
                                       encoding="utf-8")
    script = ("import('./packages/graph/dist/index.js').then(async (g) => { const fs = await import('node:fs');"
              " fs.writeFileSync(process.argv[1], g.emitTopLevel(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')))); });")
    subprocess.run(["node", "-e", script, str(out / "top.v"), str(HERE / "design.json")], cwd=ROOT, check=True)
    print(f"{len(manifest)} blocks exported to {out}; unresolved (no generation agrees with the golden model): {unresolved or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
