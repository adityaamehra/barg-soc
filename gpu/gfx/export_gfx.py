"""Choose the best generation of every graphics block, copy it into gfx/rtl/, and emit the top level of `simt-gpu-gfx`.

    python3 demos/simt-gpu/gfx/export_gfx.py [http://127.0.0.1:3021 http://127.0.0.1:3022=workspace-oc ...]

Several backends (each base=its workspace directory, default `workspace`) are searched together.

Only the blocks the graphics design adds or regenerates (build_gfx.REGENERATED: decode and dx_reg with the new fields, gfx_regs, rop_unit,
vram_mux, gfx_host, disp_ctrl) are taken from the backend; the GPU core's other blocks are used as ../rtl/ has them (BARG's output,
two hand-corrected). The choice, as in ../export_rtl.py: the newest generation that agrees with the
block's golden model, else the fewest mismatches and best verdict. Nothing is hand-corrected here: a block with no agreeing
generation is reported as unresolved. gfx/rtl/top.v is what the graph package emits from gfx/design.json.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
import export_rtl as ex  # noqa: E402
sys.path.insert(0, str(HERE))
import build_gfx  # noqa: E402
import check_golden_local  # noqa: E402

ROOT = HERE.parent.parent.parent
DESIGN = "simt-gpu-gfx"
# Each backend that generated blocks of this design, with its workspace: base[=workspace dir], default the one on :3021.
SOURCES = [(s.split("=")[0].rstrip("/"), ROOT / (s.split("=")[1] if "=" in s else "workspace") / DESIGN)
           for s in (sys.argv[1:] or ["http://127.0.0.1:3021"])]


def on(j, path, post=False):
    ex.BASE = j["base"]
    return ex.post(path) if post else ex.get(path)


def main() -> int:
    design = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
    blocks = [b for b in design["blocks"] if b["name"] in build_gfx.REGENERATED]     # the rest are the core's RTL, ../rtl/
    jobs = []
    for base, ws in SOURCES:
        ex.BASE = base
        jobs += [dict(j, base=base, ws=ws) for j in ex.get(f"/api/jobs?designId={DESIGN}") if j["state"] == "done"]
    jobs = [dict(j, order=n) for n, j in enumerate(jobs)]
    by_block: dict[str, list[dict]] = {}
    for j in jobs:
        by_block.setdefault(j["blockId"], []).append(j)
    for blk in blocks:
        for j in by_block.get(blk["id"], []):
            # always checked again: a check made before the golden model was last changed would be stale
            if (on(j, f"/api/jobs/{j['id']}/golden-check") or {}).get("status") != "pending":
                on(j, f"/api/jobs/{j['id']}/golden-check", post=True)
    deadline = time.time() + 900
    while time.time() < deadline:
        if not any((on(j, f"/api/jobs/{j['id']}/golden-check") or {}).get("status") == "pending"
                   for blk in blocks for j in by_block.get(blk["id"], [])):
            break
        time.sleep(10)
    out = HERE / "rtl"
    out.mkdir(exist_ok=True)
    manifest, unresolved = {}, []
    for blk in blocks:
        cands = []
        for j in by_block.get(blk["id"], []):
            reply = on(j, f"/api/jobs/{j['id']}/golden-check") or {}
            res, status = reply.get("result") or {}, reply.get("status", "no_golden")
            if status == "checked" and res.get("rtlCorrect") is None:
                # the backend's check stopped before judging the RTL (the generator's reference did not run): the same
                # comparison with the golden model, run here under Icarus (check_golden_local.py)
                try:
                    bad, total, first = check_golden_local.check(blk["name"], j["ws"] / "jobs" / j["id"] / "delivered.v")
                except Exception as e:                  # e.g. an older generation whose ports are not the design's now
                    bad, total, first = 1, 1, f"could not be checked: {e}"[:120]
                status = "local"
                res = {"rtlCorrect": bad == 0, "detail": f"RTL (checked here, the backend's check stopped: {res.get('detail', '')[:60]}): "
                                                         + ("agrees with the golden model on all" if not bad else f"differs from the golden model on {bad} of")
                                                         + f" {total}" + (f"; {first}" if first else "")}
            agrees = res.get("rtlCorrect") is True
            cands.append({"job": j["id"], "ws": j["ws"], "base": j["base"], "verdict": j.get("verdict"), "golden": status, "agrees": agrees,
                          "mismatches": ex.mismatches(res.get("detail", "")) if status in ("checked", "local") and not agrees else 0,
                          "detail": (res.get("detail") or "")[:140], "created": j["order"]})
        if not cands:
            raise SystemExit(f"no finished job for {blk['name']}")
        newest = sorted(cands, key=lambda c: c["created"], reverse=True)
        best = sorted(newest, key=lambda c: (0 if (c["agrees"] or c["golden"] == "no_golden") else 1, c["mismatches"],
                                             ex.RANK.get(c["verdict"], 3)))[0]
        source = best["ws"] / "jobs" / best["job"] / "delivered.v"
        if any(c["golden"] in ("checked", "local") for c in cands) and not best["agrees"]:
            # no delivered module agrees: a job may still hold one among its other candidates (with a reference that cannot tell
            # them apart, the pipeline may deliver the wrong one). Each is the generator's own output, checked here unchanged.
            for c in newest:
                for f in sorted((c["ws"] / "jobs" / c["job"] / "rtl").glob("candidate-*.v")):
                    try:
                        bad, total, _ = check_golden_local.check(blk["name"], f)
                    except Exception:
                        continue
                    if not bad:
                        best = dict(c, agrees=True, golden="local",
                                    detail=f"{f.name} of the job (not the delivered one) agrees with the golden model on all {total}")
                        source = f
                        break
                if source.name != "delivered.v":
                    break
        if any(c["golden"] in ("checked", "local") for c in cands) and not best["agrees"]:
            unresolved.append(blk["name"])
        (out / f"{blk['name']}.v").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        manifest[blk["name"]] = {**{k: best[k] for k in ("job", "base", "verdict", "golden", "agrees", "detail")},
                                 "file": source.name, "generations": len(cands)}
    (out / "manifest.json").write_text(json.dumps({"unresolved": unresolved, "blocks": manifest}, indent=2) + "\n",
                                       encoding="utf-8")
    script = ("import('./packages/graph/dist/index.js').then(async (g) => { const fs = await import('node:fs');"
              " fs.writeFileSync(process.argv[1], g.emitTopLevel(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')))); });")
    subprocess.run(["node", "-e", script, str(out / "top.v"), str(HERE / "design.json")], cwd=ROOT, check=True)
    print(f"{len(manifest)} blocks exported to {out}; unresolved: {unresolved or 'none'}")
    for name, m in manifest.items():
        print(f"  {name:10} {m['verdict']!s:18} golden {m['golden']:9} agrees {m['agrees']}  of {m['generations']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
