"""Assemble a design's Verilog from BARG's accepted outputs, for an Icarus elaboration check (reintegration).

    python3 demos/linux-soc/assemble.py <design.json> <out dir>

Each block's Verilog, in order: demos/linux-soc/rtl/<name>.v (accepted by hand-check), else the
newest port-matching finished job of the linux-core design (chosen.json from the inventory), else the stage-4 SoC's newest finished job
(the blocks the new core keeps). Every module is renamed to the block's moduleName (a block copied for two places gets its own name).
The top module is emitted by the graph package (emitTopLevel).
"""
import json, re, subprocess, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "demos" / "gpu-soc"))
import gpu_bench  # noqa: E402  (stage-4 newest finished job per block)

design = json.loads(Path(sys.argv[1]).read_text())
out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
_ch = Path(__file__).resolve().parent / "chosen.json"
if not _ch.exists(): subprocess.run([sys.executable, str(_ch.with_name("choose_jobs.py"))], check=True)
chosen = json.loads(_ch.read_text())
acc = ROOT / "demos" / "linux-soc" / "rtl"
acc_extra = [ROOT / "demos" / "quad-soc" / "rtl"]  # quad-core blocks accepted under demos/quad-soc/rtl
import re as _re
def ports_of(text):
    m = _re.search(r"module\s+(\w+)\s*\((.*?)\);", text, _re.S)
    return {nm for _, _, nm in _re.findall(r"(input|output)\s+(?:reg\s+|wire\s+)?(\[[^\]]*\]\s*)?(\w+)", m.group(2))}
def other(name, block):
    """Newest finished job, in any design of either backend, whose block has this name and this port list."""
    want = {p["name"] for p in block["ports"]}
    hits = []
    for db, ws in (("workspace/jobs.sqlite", "workspace"), ("workspace-mistral/jobs.sqlite", "workspace-mistral")):
        for jid, did, created in sqlite3.connect(ROOT / db).execute(
                "select id, design_id, created_at from jobs where state='done' and block_id in (?, ?)", (f"b_{name}", block["id"])):
            f = ROOT / ws / did / "jobs" / jid / "delivered.v"
            if f.exists() and ports_of(f.read_text()) == want:
                hits.append((created, f))
    return max(hits)[1] if hits else None
texts, source, missing = {}, {}, []
copies = json.loads((Path(sys.argv[1]).parent / "copies.json").read_text()) if (Path(sys.argv[1]).parent / "copies.json").exists() else {}
origid = json.loads((Path(sys.argv[1]).parent / "origid.json").read_text()) if (Path(sys.argv[1]).parent / "origid.json").exists() else {}  # quad: a renamed block's original id
for b in design["blocks"]:
    name, mod = b["name"], b["moduleName"]
    if b.get("ip") is not None:
        # a curated block: the wrapper the backend writes by rule, and the curated module it instantiates
        wrap = subprocess.run(["node", "-e", f"""
const ir=require('{ROOT}/packages/ir/dist/index.js');
process.stdout.write(ir.ipWrapper(JSON.parse(require('fs').readFileSync(0,'utf8'))));"""], input=json.dumps(b), capture_output=True, text=True, cwd=ROOT)
        if wrap.returncode:
            raise SystemExit("ipWrapper failed: " + wrap.stderr[:300])
        texts[mod] = wrap.stdout
        files = json.loads(subprocess.run(["node", "-e", f"""
const ir=require('{ROOT}/packages/ir/dist/index.js');
process.stdout.write(JSON.stringify(ir.ipEntry('{b["ip"]["kind"]}').files));"""], capture_output=True, text=True, cwd=ROOT, check=True).stdout)
        for f in files:       # the catalogue module(s) the wrapper instantiates, once each however many blocks use them
            texts[f] = (ROOT / "packages" / "ip" / "rtl" / f).read_text()
        source[name] = "curated " + b["ip"]["kind"]
        continue
    base = copies.get(name, re.sub(r"_(ilo|ihi|d)$", "", name) if re.sub(r"_(ilo|ihi|d)$", "", name) in ("pa_mux", "perm_check", "xfault") else name)
    accepted = next((d / f"{base}.v" for d in [acc] + acc_extra if (d / f"{base}.v").exists()), None)
    ipf = Path(sys.argv[1]).parent / "sources" / f"{mod}.v"  # `ip.js flatten` writes the Verilog of every block that came from an IP here
    if ipf.exists():
        f, how = ipf, "IP library"
    elif accepted is not None:
        f, how = accepted, "accepted"
    elif base in chosen:
        f, how = Path(chosen[base][0]), "linux-core job"
    elif (f := gpu_bench._newest("nuttx-soc-imac-16mb", origid.get(name, b["id"]))) is not None:
        how = "stage-4 job"
    elif (f := other(base, b)) is not None:
        how = "job of another design"
    else:
        missing.append(name)
        continue
    text = f.read_text()
    old = re.search(r"\bmodule\s+(\w+)", text).group(1)
    text = re.sub(rf"\bmodule\s+{re.escape(old)}\b", f"module {mod}", text, count=1)
    texts[mod] = text
    source[name] = how
if missing:
    raise SystemExit(f"no Verilog for {len(missing)} block(s): " + ", ".join(missing))
# top
ctop = subprocess.run(["node", "-e", f"""
const g=require('{ROOT}/packages/graph/dist/index.js');
const d=JSON.parse(require('fs').readFileSync('{Path(sys.argv[1]).resolve()}','utf8'));
process.stdout.write(g.emitTopLevel(d,'top'));"""], capture_output=True, text=True, cwd=ROOT)
if ctop.returncode:
    raise SystemExit("emitTopLevel failed: " + ctop.stderr[:400])
(out / "top.v").write_text(ctop.stdout)
(out / "blocks.v").write_text("\n".join(texts.values()))
import collections
print(f"{len(texts)} modules; sources: " + ", ".join(f"{k}={v}" for k, v in collections.Counter(source.values()).items()))
