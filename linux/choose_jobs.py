#!/usr/bin/env python3
"""Pick, for each linux-core block, the newest finished job of the 'linux-core-blocks' design whose module has the block's port list; write demos/linux-soc/chosen.json
({block: [delivered.v path, verdict, job id]}). assemble.py runs this when the file is missing. Run from the repository root."""
import json, re, sqlite3, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import blocks  # noqa: E402
def ports(text):
    m = re.search(r'module\s+(\w+)\s*\((.*?)\);', text, re.S)
    return {nm for _, _, nm in re.findall(r'(input|output)\s+(?:reg\s+|wire\s+)?(\[[^\]]*\]\s*)?(\w+)', m.group(2))}
rows = []
for db, ws in (("workspace/jobs.sqlite", "workspace"), ("workspace-mistral/jobs.sqlite", "workspace-mistral")):
    if not (ROOT / db).exists(): continue
    for jid, bid, v, created in sqlite3.connect(ROOT / db).execute("select id,block_id,coalesce(verdict,'-'),created_at from jobs where design_id='linux-core-blocks' and state='done'"):
        f = ROOT / ws / 'linux-core-blocks' / 'jobs' / jid / 'delivered.v'
        if f.exists(): rows.append((bid[2:], created, v, jid, f))
chosen = {}
for b in blocks.BLOCKS:
    spec = {p['name'] for p in b['ports']}
    c = sorted([r for r in rows if r[0] == b['name'] and ports(r[4].read_text()) == spec], key=lambda r: r[1], reverse=True)
    if c: chosen[b['name']] = [str(c[0][4]), c[0][2], c[0][3]]
(HERE / "chosen.json").write_text(json.dumps(chosen, indent=1))
print(f"{len(chosen)} blocks -> {HERE / 'chosen.json'}")
