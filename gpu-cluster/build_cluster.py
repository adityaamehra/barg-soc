"""The GPU cluster: ten SIMT GPUs (IP `simt_gpu`) behind one host bus, as one design (`gpu-cluster`).

    python3 demos/gpu-cluster/build_cluster.py [--cores 10]    # writes demos/gpu-cluster/design.json

The cluster takes the same ports as the SoC's `gpu_bridge` (the SoC's memory stage) and gives the same status outputs as one GPU, so it
replaces one GPU in the GPU SoC. Inside: the SoC's `gpu_bridge` (unchanged), ten placed `simt_gpu` IPs, and four new blocks:
  cluster_addr   addr -> local_addr (slot bits 24:21 cleared, which is the one-GPU address the bridge translates) and slot
  cluster_fan    host_en -> one enable per core (slot = core number; slot 15 = all cores)
  cluster_rmux   the cores' read data: the registered slot picks the answering core
  cluster_status running (any), done (all), error (any), diverged (any)
Each core has its own memories (instruction, global, shared, video, depth, texture); the host addresses core k at 0x3000_0000 +
k * 0x20_0000 (2 MB slots, bits 24:21), slot 15 (0x31E0_0000) writes all cores at once. The display shown is core 0's.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "demos" / "gpu-soc"))
from build_gpu_soc import GPU_BRIDGE, block, i, o, port  # noqa: E402

N = int(sys.argv[sys.argv.index("--cores") + 1]) if "--cores" in sys.argv else 10
W = 32

CLUSTER_ADDR = block("b_cl_addr", "cluster_addr", """
    Combinational. addr is a 32-bit address. slot is addr bits 24:21 (4 bits). local_addr is addr with bits 24:21 set to 0 and every
    other bit unchanged. No clock, no reset, no state.
""", [i("addr", W, "addr"), o("local_addr", W, "addr"), o("slot", 4, "control")])

CLUSTER_FAN = block("b_cl_fan", "cluster_fan", f"""
    Combinational. host_en is a bus request; slot (4 bits) names the core it is for. en0 .. en{N - 1} are one bit each: en<k> is 1
    when host_en is 1 and slot is k or 15 (slot 15 is every core), and 0 otherwise. A slot from {N} to 14 names no core: every
    output is 0. No clock, no reset, no state.
""", [i("host_en", 1, "valid"), i("slot", 4, "control")] + [o(f"en{k}", 1, "valid") for k in range(N)])

CLUSTER_RMUX = block("b_cl_rmux", "cluster_rmux", f"""
    The read data of {N} cores on one bus. A core answers a read one cycle after the request, so the multiplexer remembers which core
    the request was for. One register, slot_r (4 bits): at each rising clock edge it becomes 0 when rst is 1, else takes slot when
    host_en is 1 and host_we is 0 (a read request), else keeps its value. sel is slot_r, except that slot_r = 15 gives sel = 0.
    rdata is rdata<sel> and rvalid is rvalid<sel> when sel is from 0 to {N - 1} (the inputs rdata0 .. rdata{N - 1}, 32 bits each, and
    rvalid0 .. rvalid{N - 1}, 1 bit each); when sel is from {N} to 14, rdata is 0 and rvalid is 0. rdata and rvalid depend on the
    held slot_r and the inputs only, not on slot, host_en or host_we of this cycle.
""", [port("p_clk", "clk", "in", 1, "clock"), port("p_rst", "rst", "in", 1, "reset"), i("host_en", 1, "valid"),
      i("host_we", 1, "control"), i("slot", 4, "control")] + [i(f"rdata{k}", W) for k in range(N)] +
      [i(f"rvalid{k}", 1, "valid") for k in range(N)] + [o("rdata", W), o("rvalid", 1, "valid")], reset="sync", latency=1)

CLUSTER_STATUS = block("b_cl_status", "cluster_status", f"""
    Combinational. The inputs are the status bits of {N} cores, one bit each: running0 .. running{N - 1}, done0 .. done{N - 1}, error0 ..
    error{N - 1} and diverged0 .. diverged{N - 1}. running is 1 when any running<k> is 1. done is 1 when every done<k> is 1. error is
    1 when any error<k> is 1. diverged is 1 when any diverged<k> is 1. No clock, no reset, no state.
""", [i(f"{p}{k}", 1, "control") for p in ("running", "done", "error", "diverged") for k in range(N)] +
      [o("running", 1, "control"), o("done", 1, "control"), o("error", 1, "control"), o("diverged", 1, "control")])


def design() -> dict:
    gfx = json.loads((ROOT / "demos" / "simt-gpu" / "gfx" / "design.json").read_text())
    gp = [{k: v for k, v in p.items() if k != "blockId"} for p in gfx["topLevelPorts"]]
    index = json.loads((ROOT / "workspace" / "ip-library" / "index.json").read_text())["simt_gpu"]["versions"][-1]
    ref = {"name": "simt_gpu", "version": index["version"], "sha256": index["sha256"]}
    blocks = [CLUSTER_ADDR, CLUSTER_FAN, CLUSTER_RMUX, CLUSTER_STATUS, GPU_BRIDGE]
    for k in range(N):
        blocks.append({"id": f"b_gpu{k}", "name": f"u_gpu{k}", "tier": "T1", "moduleName": f"simt_gpu_core{k}", "clockDomain": "main",
                       "resetStyle": "none", "latencyCycles": 0, "verified": True, "ports": gp, "ipRef": ref,
                       "description": f"IP simt_gpu v{ref['version']}: core {k} of the cluster, not generated again"})
    nets: list[dict] = []

    def net(name, width, driver, sinks):
        nets.append({"id": f"n_{len(nets) + 1:03d}", "name": name, "width": width, "driver": driver, "sinks": sinks,
                     "kind": "bus" if width > 1 else "wire", "pipelineStage": 0})

    def end(b, p):
        return {"blockId": b, "portId": p}

    top = lambda p: end(None, p)  # noqa: E731
    gpus = [f"b_gpu{k}" for k in range(N)]
    tops = [port("t_clk", "clk", "in", 1, "clock"), port("t_rst", "rst", "in", 1, "reset"),
            port("t_gpu_we", "gpu_we", "in", 1, "control"), port("t_gpu_re", "gpu_re", "in", 1, "control"),
            port("t_addr", "addr", "in", W, "addr"), port("t_wdata", "wdata", "in", W, "data"),
            port("t_memtype", "memtype", "in", 3, "control"), port("t_rdata", "rdata", "out", W, "data")]
    tops = [{**p, "blockId": None} for p in tops]
    net("clock", 1, top("t_clk"), [end("b_cl_rmux", "p_clk"), end("b_gpu_bridge", "p_clk")] + [end(g, "t_clk") for g in gpus])
    net("reset", 1, top("t_rst"), [end("b_cl_rmux", "p_rst"), end("b_gpu_bridge", "p_rst")] + [end(g, "t_rst") for g in gpus])
    net("gpu_we", 1, top("t_gpu_we"), [end("b_gpu_bridge", "p_gpu_we")])
    net("gpu_re", 1, top("t_gpu_re"), [end("b_gpu_bridge", "p_gpu_re")])
    net("addr", W, top("t_addr"), [end("b_cl_addr", "p_addr")])
    net("wdata", W, top("t_wdata"), [end("b_gpu_bridge", "p_wdata")])
    net("memtype", 3, top("t_memtype"), [end("b_gpu_bridge", "p_memtype")])
    net("local_addr", W, end("b_cl_addr", "p_local_addr"), [end("b_gpu_bridge", "p_addr")])
    net("slot", 4, end("b_cl_addr", "p_slot"), [end("b_cl_fan", "p_slot"), end("b_cl_rmux", "p_slot")])
    net("host_en", 1, end("b_gpu_bridge", "p_host_en"), [end("b_cl_fan", "p_host_en"), end("b_cl_rmux", "p_host_en")])
    net("host_we", 1, end("b_gpu_bridge", "p_host_we"), [end("b_cl_rmux", "p_host_we")] + [end(g, "t_host_we") for g in gpus])
    net("host_addr", W, end("b_gpu_bridge", "p_host_addr"), [end(g, "t_host_addr") for g in gpus])
    net("host_wdata", W, end("b_gpu_bridge", "p_host_wdata"), [end(g, "t_host_wdata") for g in gpus])
    net("host_rdata", W, end("b_cl_rmux", "p_rdata"), [end("b_gpu_bridge", "p_host_rdata")])
    net("host_rvalid", 1, end("b_cl_rmux", "p_rvalid"), [end("b_gpu_bridge", "p_host_rvalid")])
    net("rdata", W, end("b_gpu_bridge", "p_rdata"), [top("t_rdata")])
    for k, g in enumerate(gpus):
        net(f"en{k}", 1, end("b_cl_fan", f"p_en{k}"), [end(g, "t_host_en")])
        net(f"rdata{k}", W, end(g, "t_host_rdata"), [end("b_cl_rmux", f"p_rdata{k}")])
        net(f"rvalid{k}", 1, end(g, "t_host_rvalid"), [end("b_cl_rmux", f"p_rvalid{k}")])
        for s in ("running", "done", "error", "diverged"):
            net(f"{s}{k}", 1, end(g, f"t_{s}"), [end("b_cl_status", f"p_{s}{k}")])
    for s in ("running", "done", "error", "diverged"):
        tops.append({**port(f"t_gpu_{s}", f"gpu_{s}", "out", 1, "control"), "blockId": None})
        net(f"gpu_{s}", 1, end("b_cl_status", f"p_{s}"), [top(f"t_gpu_{s}")])
    for s, w in (("hsync", 1), ("vsync", 1), ("de", 1), ("rgb", 16)):
        tops.append({**port(f"t_gpu_{s}", f"gpu_{s}", "out", w, "control" if w == 1 else "data"), "blockId": None})
        net(f"gpu_{s}", w, end("b_gpu0", f"t_{s}"), [top(f"t_gpu_{s}")])
    return {"id": "gpu-cluster", "name": f"GPU cluster ({N} SIMT GPUs, one host bus)", "version": 1,
            "createdAt": "2026-11-20T00:00:00.000Z", "blocks": blocks, "nets": nets, "topLevelPorts": tops,
            "constraintGroups": [], "constraints": []}


if __name__ == "__main__":
    d = design()
    out = HERE / "design.json"
    out.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    print(f"{out}: {len(d['blocks'])} blocks, {len(d['nets'])} nets")
