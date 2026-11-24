"""Install every golden model on the backend and check every finished generation of every block against it.

    python3 demos/simt-gpu/golden_report.py [http://127.0.0.1:3001]

Prints, per block, each generation (oldest first) with its verdict and what the golden check said. A golden model's own
directed `vectors(rng)` / `traces(rng)` are used by the check, so a generation is judged on the behaviour random inputs miss.
"""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3001").rstrip("/")
DESIGN = "simt-gpu"


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"content-type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError:
        return None


def main() -> int:
    design = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
    call("PUT", f"/api/designs/{DESIGN}", design)
    for blk in design["blocks"]:
        golden = HERE / "golden" / f"{blk['name']}.py"
        if golden.exists():
            call("PUT", f"/api/designs/{DESIGN}/blocks/{blk['id']}/golden",
                 {"code": golden.read_text(encoding="utf-8"), "functionName": f"golden_{blk['name']}"})
    jobs = [j for j in call("GET", f"/api/jobs?designId={DESIGN}") if j["state"] == "done"]
    for j in jobs:
        call("POST", f"/api/jobs/{j['id']}/golden-check", {})
    deadline = time.time() + 1800
    while time.time() < deadline:
        if not any((call("GET", f"/api/jobs/{j['id']}/golden-check") or {}).get("status") == "pending" for j in jobs):
            break
        time.sleep(15)
    names = {b["id"]: b["name"] for b in design["blocks"]}
    for blk in design["blocks"]:
        mine = [j for j in jobs if j["blockId"] == blk["id"]]
        if not (HERE / "golden" / f"{blk['name']}.py").exists():
            print(f"{blk['name']:14} template block, no golden model ({len(mine)} generation(s), {mine[-1].get('verdict')})")
            continue
        print(f"{blk['name']:14}")
        for j in mine:
            r = (call("GET", f"/api/jobs/{j['id']}/golden-check") or {}).get("result") or {}
            print(f"    {j['id'][:8]} {str(j.get('verdict')):16} {(r.get('detail') or 'no result')[:110]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
