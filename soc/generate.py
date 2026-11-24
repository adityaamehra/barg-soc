"""Install the golden models of the quad-core blocks and start their generation on a running backend.

    python3 demos/quad-soc/generate.py [--only=a,b] [--candidates=N] [--provider=NAME] [http://127.0.0.1:3021]

Two designs on the backend: `rv-core-mc` (design-core.json: the three new core blocks) and `quad-blocks` (the six new shared blocks, no
nets: only the blocks are generated; the quad design itself places IPs). Golden models (demos/quad-soc/golden/) are never shown to the generator.
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
args = [a for a in sys.argv[1:] if not a.startswith("--")]
opt = lambda k, d=None: next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith(f"--{k}=")), d)  # noqa: E731
BASE = (args[0] if args else "http://127.0.0.1:3021").rstrip("/")
wanted = None if opt("only") is None else set(opt("only").split(","))
provider, candidates = opt("provider"), int(opt("candidates", 1))
STEPS = {"plic8": 600, "mip_merge_s": 128, "plic5": 600, "region_decode_w": 300, "pdev_bus3": 200, "ps2_rx": 600, "ps2_tx": 700, "ps2_regs": 400, "ps2_fifo": 300, "ps2_ctl": 300, "bus_ctl_i": 200, "vga_timing": 400, "px_pick": 128, "disp_regs": 300, "pdev_bus2": 200, "l2_ctl_fw": 700, "l3_ctl_fw": 700, "clint4_div": 600, "ifault_pmp": 300, "pmp_regs16": 400, "pmp_check": 300, "wfi_wake2": 300, "l3_ctl_wa": 700, "wfi_wake": 128, "postw": 300, "tlb32": 500, "pdev_bus": 128, "gpio_regs": 500, "spi_regs": 500, "i2c_regs": 500, "gshare_tbl": 700, "bp_pipe": 300, "l2_ctl": 700, "l3_ctl": 700, "dcache_ctl": 500, "fp_dwseq": 400, "fp_pipe": 300, "fp_seq": 400, "fp_csr": 500, "fregfile": 400, "uart16550f": 700, "mem_arb": 700, "ifetch_ctl": 500, "rsp_hold": 300, "word_addr24": 64, "pack16w": 64, "plic4": 600, "clint4": 600, "bus_arb": 300, "bus_mux4": 100, "core_gate": 20}


def call(method, path, body=None):
    request = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                     headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return {"error": error.read().decode()[:300], "status": error.code}


import build_quad as bq  # noqa: E402
import memblocks as mb  # noqa: E402
import periphblocks as pb  # noqa: E402
import fpblocks as fb  # noqa: E402
import bpblocks as bpb  # noqa: E402
import devblocks as dvb  # noqa: E402
import dispblocks as dsp  # noqa: E402
import ps2blocks as ps2  # noqa: E402

core = json.loads((HERE / "design-core.json").read_text())
quad_blocks = [bq.RSV_GATE, bq.CLINT_DECODE4, bq.CLINT4, bq.BUS_ARB, bq.BUS_MUX4, bq.CORE_GATE, bq.HART_CFG, bq.PLIC4, bq.WORD_ADDR24, bq.PACK16W, *mb.BLOCKS, *pb.BLOCKS, *fb.BLOCKS, *bpb.BLOCKS, *dvb.BLOCKS, *dsp.BLOCKS, *ps2.BLOCKS]
def standalone(blocks):
    """Each block's every port wired to a top-level port of its own (the design only carries the blocks for generation)."""
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


qt, qn = standalone(quad_blocks)
designs = {"rv-core-mc": core,
           "quad-blocks": {**{k: v for k, v in core.items() if k not in ("blocks", "nets", "topLevelPorts")}, "id": "quad-blocks",
                           "name": "Blocks of the quad-core SoC (generation only)", "blocks": quad_blocks, "nets": qn, "topLevelPorts": qt}}
import time  # noqa: E402
for did, d in designs.items():
    d = {**d, "version": int(time.time())}   # a new version each upload: the backend's job validation caches the design by version
    r = call("PUT", f"/api/designs/{did}", d)
    if "error" in r:
        print(did, "NOT uploaded:", r)
        continue
    for blk in d["blocks"]:
        name = blk["name"]
        golden = HERE / "golden" / f"{name}.py"
        if not golden.exists() or (wanted is not None and name not in wanted):
            continue
        r = call("PUT", f"/api/designs/{did}/blocks/{blk['id']}/golden", {"code": golden.read_text(encoding="utf-8"), "functionName": f"golden_{name}"})
        if "error" in r:
            print(f"{name:16} golden model NOT installed: {r}")
            continue
        reply = call("POST", f"/api/blocks/{blk['id']}/generate", {"designId": did, "options": {
            "stimulusSteps": STEPS.get(name, 128), **({"ambiguitySamples": 0, "referenceVote": False, "fromReference": False, "disable": ["ambiguity", "mutation", "probe", "metamorphic", "localize"]} if "--lean" in sys.argv else {}), "candidates": candidates, **({} if provider is None else {"provider": provider}),
            **({} if opt("patch_from") is None else {"patch": {"rtl": Path(opt("patch_from")).read_text(), "note": opt("note", "apply the change the description now asks for")}})}})
        print(f"{name:16} {reply.get('jobId', reply)}")
