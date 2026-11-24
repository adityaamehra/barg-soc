"""Install the golden models of the final SoC's shared blocks (blocks.py) and start their generation on a running backend.

    python3 demos/soc-final/generate.py [--only=a,b] [--candidates=N] [--provider=NAME] [http://127.0.0.1:3021]
    python3 demos/linux-soc/generate.py --only=name --patch_from=demos/linux-soc/rtl/old.v --note="what to change" ...   # patch mode: edit blocks against existing RTL
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import blocks as fb  # noqa: E402
DID = "linux-core-blocks"

args = [a for a in sys.argv[1:] if not a.startswith("--")]
opt = lambda k, d=None: next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith(f"--{k}=")), d)  # noqa: E731
BASE = (args[0] if args else "http://127.0.0.1:3021").rstrip("/")
wanted = None if opt("only") is None else set(opt("only").split(","))


def call(method, path, body=None):
    r = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                               headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:300]}


def standalone(blocks):
    tops, nets = [], []
    for b in blocks:
        for pt in b["ports"]:
            tid = f"t_{b['name']}_{pt['name']}"
            tops.append({**{k: v for k, v in pt.items() if k != "id"}, "id": tid, "name": f"{b['name']}_{pt['name']}", "blockId": None})
            here, top = {"blockId": b["id"], "portId": pt["id"]}, {"blockId": None, "portId": tid}
            drv, snk = (top, here) if pt["direction"] == "in" else (here, top)
            nets.append({"id": f"n_{len(nets) + 1:03d}", "name": tid[2:], "width": pt["width"], "driver": drv, "sinks": [snk],
                         "kind": "bus" if pt["width"] > 1 else "wire", "pipelineStage": 0})
    return tops, nets


tops, nets = standalone(fb.BLOCKS)
d = {"id": DID, "name": "Core with S-mode and MMU: new blocks (generation only)", "version": 1, "createdAt": "2026-11-20T00:00:00.000Z",
     "blocks": fb.BLOCKS, "nets": nets, "topLevelPorts": tops, "constraintGroups": [], "constraints": []}
(HERE / "design-blocks.json").write_text(json.dumps(d, indent=1))
print(str(call("PUT", f"/api/designs/{DID}", d))[:60])
for b in fb.BLOCKS:
    n = b["name"]
    if wanted is not None and n not in wanted:
        continue
    g = HERE / "golden" / f"{n}.py"
    r = call("PUT", f"/api/designs/{DID}/blocks/{b['id']}/golden", {"code": g.read_text(), "functionName": f"golden_{n}"}) if g.exists() else {}
    if "error" in r:
        print(n, r)
        continue
    print(n, call("POST", f"/api/blocks/{b['id']}/generate", {"designId": DID, "options": {
        "stimulusSteps": {"trap_unit": 600, "csr_rmux": 600, "csr_sel2": 400}.get(n, 300), **({"ambiguitySamples": 0, "referenceVote": False, "fromReference": False, "disable": ["ambiguity", "mutation", "probe", "metamorphic", "localize"]} if "--lean" in sys.argv else {}), "candidates": int(opt("candidates", 2)), **({} if opt("provider") is None else {"provider": opt("provider")}),
        **({} if opt("patch_from") is None else {"patch": {"rtl": Path(opt("patch_from")).read_text(), "note": opt("note", "apply the change the description now asks for")}})}}))
