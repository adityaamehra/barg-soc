"""Install the golden models and start generation for every block of the GPU design on a running backend.

    python3 demos/simt-gpu/generate.py [--only=name,name] [--candidates=N] [--no-golden] [http://127.0.0.1:3001]

The golden models (golden/<block>.py, golden function golden_<block>) are stored beside the design for the golden check after
each job; they are never shown to the generator. The storage and counter blocks are built from their templates and have none.
Clocked blocks get a longer test sequence; the divider's must cover several 34-cycle divisions.
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
args = [a for a in sys.argv[1:] if not a.startswith("--")]
only = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--only=")), None)
candidates = int(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--candidates=")), 1))
BASE = (args[0] if args else "http://127.0.0.1:3001").rstrip("/")
DESIGN = "simt-gpu"
STEPS = {"vdiv": 800, "lsu": 400, "warp_table": 400, "warp_sched": 300, "ipdom": 400, "barrier_unit": 300,
         "tensor_unit": 300, "host_if": 400, "sf_reg": 200, "dx_reg": 200}


def call(method, path, body=None):
    request = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                     headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return {"error": error.read().decode()[:300], "status": error.code}


design = call("GET", f"/api/designs/{DESIGN}")
wanted = None if only is None else set(only.split(","))
for blk in design["blocks"]:
    name = blk["name"]
    if wanted is not None and name not in wanted:
        continue
    golden = HERE / "golden" / f"{name}.py"
    if golden.exists() and "--no-golden" not in sys.argv:
        r = call("PUT", f"/api/designs/{DESIGN}/blocks/{blk['id']}/golden",
                 {"code": golden.read_text(encoding="utf-8"), "functionName": f"golden_{name}"})
        if "error" in r:
            print(f"{name:14} golden model NOT installed: {r}")
    options = {"stimulusSteps": STEPS.get(name, 128), "candidates": candidates}
    reply = call("POST", f"/api/blocks/{blk['id']}/generate", {"designId": DESIGN, "options": options})
    print(f"{name:14} {reply.get('jobId', reply)} {reply.get('state', '')}")
