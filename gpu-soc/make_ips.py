"""The GPU SoC rebuilt from IPs: the SIMT GPU and the NuttX SoC kept in the IP library, the GPU SoC placing them as blocks.

    python3 demos/gpu-soc/make_ips.py [--workspace workspace]

1. `simt_gpu`: the GPU with graphics (demos/simt-gpu/gfx/design.json, 82 blocks), each block's Verilog as gpu_bench takes it
   (gfx/rtl, else the core's rtl), with the verdict and evidence from the manifests. Two core blocks, lsu and simt_ctrl, were
   corrected by hand in the core's own stage; the IP records them as HAND_CORRECTED.
2. `nuttx_soc` v1: the stage-4 SoC (demos/nuttx-soc/design-a-16mb.json, 70 blocks), each block's best accepted run across the two
   backends' workspaces (gpu_bench._newest).
3. The GPU SoC with the GPU placed as one block (`design-hier-pre.json`): the SoC's blocks (region_decode, bus_ctl and io_mux in their
   G3 versions), gpu_bridge, and `u_simt_gpu`.
4. `nuttx_soc` v2: the SoC side of that (the stage-4 SoC with the G3 blocks and a port for the GPU), saved as a second version of
   `nuttx_soc` (v1 kept), and the design with it collapsed into one block (`design-hier.json`): u_nuttx_soc, gpu_bridge, u_simt_gpu.

Nothing is generated: every block's Verilog is one BARG already generated and accepted.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
GPU = ROOT / "demos" / "simt-gpu"
sys.path.insert(0, str(HERE))
import gpu_bench  # noqa: E402

CLI = ROOT / "packages" / "backend" / "dist" / "cli" / "ip.js"
OUT = HERE / "ip"


def ip(*args: str) -> str:
    r = subprocess.run(["node", str(CLI), *args], capture_output=True, text=True, cwd=ROOT)
    print(r.stdout.strip(), r.stderr.strip(), sep="\n" if r.stderr.strip() else "")
    if r.returncode:
        raise SystemExit(f"ip {args[0]} failed")
    return r.stdout


def gpu_map() -> dict:
    gfx = json.loads((GPU / "gfx" / "rtl" / "manifest.json").read_text())["blocks"]
    core = json.loads((GPU / "rtl" / "manifest.json").read_text())["blocks"]
    design = json.loads((GPU / "gfx" / "design.json").read_text())
    out = {}
    for b in design["blocks"]:
        n = b["name"]
        if (GPU / "gfx" / "rtl" / f"{n}.v").exists():
            rtl, m, where = GPU / "gfx" / "rtl" / f"{n}.v", gfx.get(n, {}), "demos/simt-gpu/gfx/rtl"
        else:
            rtl, m, where = GPU / "rtl" / f"{n}.v", core.get(n, {}), "demos/simt-gpu/rtl"
        if m.get("hand_corrected"):
            verdict, evidence = "HAND_CORRECTED", ("corrected by hand in the GPU core's stage; "
                                                  "agrees with its golden model under directed stimulus")
        else:
            verdict = m.get("verdict", "VERIFIED")
            evidence = verdict + (f"; {m['detail']}" if m.get("detail") else "")
        entry = {"rtl": str(rtl), "verdict": verdict, "evidence": evidence, "from": f"{where}/{n}.v (job {m.get('job') or m.get('chosen') or '?'})"}
        for gdir in (GPU / "gfx" / "golden", GPU / "golden"):
            if (gdir / f"{n}.py").exists():
                entry["golden"] = {"path": str(gdir / f"{n}.py"), "functionName": f"golden_{n}"}
                break
        out[n] = entry
    return out


def soc_entry(design_id: str, block_id: str) -> dict:
    f = gpu_bench._newest(design_id, block_id)
    if f is None:
        raise SystemExit(f"no accepted run of {block_id}")
    job = f.parent.name
    ws = f.parents[3]
    verdict = sqlite3.connect(ws / "jobs.sqlite").execute("select verdict from jobs where id=?", (job,)).fetchone()[0]
    evidence = verdict
    check = f.parent / "golden-check.json"
    if check.exists():
        c = json.loads(check.read_text())
        evidence += f"; {c.get('detail', '')}"
        if verdict not in ("VERIFIED", "VERIFIED_LOWCONF") and c.get("rtlCorrect") is not True:
            raise SystemExit(f"{block_id}: {verdict} and no agreeing golden check")
    return {"rtl": str(f), "verdict": verdict, "evidence": evidence, "from": f"{ws.name}/{design_id}/jobs/{job}"}


def soc_map(design: dict) -> dict:
    return {b["name"]: soc_entry(design["id"], b["id"]) for b in design["blocks"]}


def g3_map(design: dict, names: list[str]) -> dict:
    """The SoC side of the GPU SoC: stage-4 blocks as in soc_map, the G3 blocks from gpu_bench (golden-checked here)."""
    srcs, manifest = gpu_bench.sources()
    stage4 = {b["name"]: b for b in json.loads(gpu_bench.STAGE4.read_text())["blocks"]}
    out = {}
    for n in names:
        if n in gpu_bench.G3_BLOCKS:
            p = OUT / "g3" / f"{n}.v"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(srcs[n])
            out[n] = {"rtl": str(p), "verdict": "REVIEW", "evidence": f"agrees with its golden model ({manifest[n]['golden']})",
                      "from": manifest[n]["from"], "golden": {"path": str(HERE / "golden" / f"{n}.py"), "functionName": f"golden_{n}"}}
        else:
            out[n] = soc_entry("nuttx-soc-imac-16mb", stage4[n]["id"])
    return out


def hier_pre(gpu_ref: dict) -> dict:
    """design.json with the GPU's blocks replaced by one block that places simt_gpu (ports matched by the GPU's own top-level ports)."""
    flat = json.loads((HERE / "design.json").read_text())
    gfx = json.loads((GPU / "gfx" / "design.json").read_text())
    gpu_ports = [{k: v for k, v in p.items() if k != "blockId"} for p in gfx["topLevelPorts"]]
    blk = {"id": "b_gpu", "name": "u_simt_gpu", "tier": "T1", "moduleName": "simt_gpu", "clockDomain": "main", "resetStyle": "none",
           "latencyCycles": 0, "verified": True, "ports": gpu_ports, "ipRef": gpu_ref,
           "description": f"IP simt_gpu v{gpu_ref['version']}: {len(gfx['blocks'])} blocks, not generated again"}
    is_gpu = lambda e: e["blockId"] is not None and e["blockId"].startswith("b_g_")  # noqa: E731
    # which GPU top-level port each GPU-internal endpoint stood for: the GPU design's nets from/to its top-level ports
    port_of = {}
    for n in gfx["nets"]:
        ends = [n["driver"], *n["sinks"]]
        tops = [e["portId"] for e in ends if e["blockId"] is None]
        for e in ends:
            if e["blockId"] is not None:
                for t in tops:
                    port_of.setdefault(("b_g_" + e["blockId"][2:], e["portId"]), t)
    nets = []
    for n in flat["nets"]:
        ends = [n["driver"], *n["sinks"]]
        if not any(is_gpu(e) for e in ends):
            nets.append(n)
            continue
        if all(is_gpu(e) for e in ends):
            continue  # inside the GPU
        drv = n["driver"]
        outside = [s for s in n["sinks"] if not is_gpu(s)]
        if is_gpu(drv):
            # a GPU output: driven by the GPU block's port
            port = port_of[(drv["blockId"], drv["portId"])]
            if outside:
                nets.append({**n, "driver": {"blockId": "b_gpu", "portId": port}, "sinks": outside})
        else:
            # into the GPU: one sink on the GPU block's port (clock, reset, host bus), whatever it fed inside
            ports = sorted({port_of[(s["blockId"], s["portId"])] for s in n["sinks"] if is_gpu(s)})
            assert len(ports) == 1, (n["name"], ports)
            nets.append({**n, "sinks": outside + [{"blockId": "b_gpu", "portId": ports[0]}]})
    blocks = [b for b in flat["blocks"] if not b["id"].startswith("b_g_")] + [blk]
    return {**flat, "id": "gpu-soc-hier", "name": "GPU SoC from IPs (NuttX SoC + SIMT GPU)", "blocks": blocks, "nets": nets}


def main() -> None:
    ws = sys.argv[sys.argv.index("--workspace") + 1] if "--workspace" in sys.argv else str(ROOT / "workspace")
    OUT.mkdir(exist_ok=True)
    (OUT / "map-gpu.json").write_text(json.dumps(gpu_map(), indent=1))
    ip("create", "--workspace", ws, "--design", str(GPU / "gfx" / "design.json"), "--name", "simt_gpu",
       "--note", "SIMT GPU (4 warps x 4 lanes, RV32IM+SIMT, int8 tensor) with graphics: raster, texture, blend, depth, 320x240 RGB565 display",
       "--sources", str(OUT / "map-gpu.json"))
    stage4 = json.loads(gpu_bench.STAGE4.read_text())
    (OUT / "map-soc.json").write_text(json.dumps(soc_map(stage4), indent=1))
    ip("create", "--workspace", ws, "--design", str(gpu_bench.STAGE4), "--name", "nuttx_soc",
       "--note", "NuttX SoC stage 4: RV32IMAC core, 16 MB RAM, UART 16550, CLINT, PLIC", "--sources", str(OUT / "map-soc.json"))

    index = json.loads((Path(ws) / "ip-library" / "index.json").read_text())
    v = index["simt_gpu"]["versions"][-1]
    pre = hier_pre({"name": "simt_gpu", "version": v["version"], "sha256": v["sha256"]})
    (OUT / "design-hier-pre.json").write_text(json.dumps(pre, indent=1))
    soc_ids = [b["id"] for b in pre["blocks"] if b["id"] not in ("b_gpu", "b_gpu_bridge")]
    (OUT / "soc-blocks.txt").write_text("\n".join(soc_ids))
    names = [b["name"] for b in pre["blocks"] if b["id"] in soc_ids]
    (OUT / "map-soc-g3.json").write_text(json.dumps(g3_map(pre, names), indent=1))
    ip("create", "--workspace", ws, "--design", str(OUT / "design-hier-pre.json"), "--name", "nuttx_soc",
       "--note", "NuttX SoC stage 4 with a GPU port (region_decode, bus_ctl, io_mux in their G3 versions)",
       "--sources", str(OUT / "map-soc-g3.json"), "--blocks", f"@{OUT / 'soc-blocks.txt'}", "--collapse-out", str(HERE / "design-hier.json"))
    ip("list", "--workspace", ws)


if __name__ == "__main__":
    main()
