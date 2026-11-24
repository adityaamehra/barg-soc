"""Install the golden models of the cluster blocks and start their generation on a running backend.

    python3 demos/gpu-soc/generate.py [--only=name,name] [--candidates=N] [--provider=NAME] [http://127.0.0.1:3021]

--provider picks the model for these jobs on a backend that serves several (e.g. nim-glm-low@nvidia/nemotron-3.5-bolt-e4b);
without it the backend's own --provider is used. Run the script once per model, each with its own --only list.

Only blocks with a golden model in demos/gpu-cluster/golden/ are generated (the four the cluster adds); the SoC's other blocks
come from the stage-4 jobs and the GPU's from demos/simt-gpu. The golden models are never shown to the generator.
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
args = [a for a in sys.argv[1:] if not a.startswith("--")]
only = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--only=")), None)
provider = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--provider=")), None)
candidates = int(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--candidates=")), 1))
BASE = (args[0] if args else "http://127.0.0.1:3021").rstrip("/")
DESIGN = "gpu-cluster"
STEPS = {"cluster_rmux": 300, "cluster_status": 200, "cluster_fan": 100, "cluster_addr": 100}


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
    golden = HERE / "golden" / f"{name}.py"
    if not golden.exists() or (wanted is not None and name not in wanted):
        continue
    r = call("PUT", f"/api/designs/{DESIGN}/blocks/{blk['id']}/golden",
             {"code": golden.read_text(encoding="utf-8"), "functionName": f"golden_{name}"})
    if "error" in r:
        print(f"{name:12} golden model NOT installed: {r}")
        continue
    reply = call("POST", f"/api/blocks/{blk['id']}/generate",
                 {"designId": DESIGN, "options": {"stimulusSteps": STEPS.get(name, 128), "candidates": candidates,
                                                             **({} if provider is None else {"provider": provider})}})
    print(f"{name:12} {reply.get('jobId', reply)} {reply.get('state', '')}")
