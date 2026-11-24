"""Golden-check generated blocks of the quad-blocks design and accept those that agree: copies delivered.v into demos/quad-soc/rtl/<name>.v and logs
the block in rtl/ACCEPTED.md.     python3 demos/quad-soc/accept.py name=jobid [name=jobid ...]"""
import json, os, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "demos" / "gpu-soc"), str(ROOT / "demos" / "quad-soc")]
import check_golden_local as c  # noqa: E402
import build_quad as bq  # noqa: E402
import memblocks as mb  # noqa: E402
import periphblocks as pb  # noqa: E402
import fpblocks as fb  # noqa: E402
import bpblocks as bpb  # noqa: E402
import devblocks as dvb  # noqa: E402
import dispblocks as dsp  # noqa: E402
import ps2blocks as ps2  # noqa: E402

spec = Path("/tmp/quad_blocks_spec.json")
spec.write_text(json.dumps({"blocks": [bq.WORD_ADDR24, bq.PACK16W, bq.PLIC4, *mb.BLOCKS, *pb.BLOCKS, *fb.BLOCKS, *bpb.BLOCKS, *dvb.BLOCKS, *dsp.BLOCKS, *ps2.BLOCKS]}))
db = sqlite3.connect(ROOT / os.environ.get("BARG_WS", "workspace") / "jobs.sqlite")
bad = 0
for arg in sys.argv[1:]:
    name, jid = arg.split("=")
    verdict = db.execute("select coalesce(verdict,'-') from jobs where id=?", (jid,)).fetchone()[0]
    f = ROOT / os.environ.get("BARG_WS", "workspace") / "quad-blocks" / "jobs" / jid / "delivered.v"
    r = c.check(name, f, golden_dir=ROOT / "demos" / "quad-soc" / "golden", design_path=spec)
    if r[0] == 0:
        (ROOT / "demos" / "quad-soc" / "rtl" / f"{name}.v").write_text(f.read_text())
        with open(ROOT / "demos" / "quad-soc" / "rtl" / "ACCEPTED.md", "a") as log:
            log.write(f"| {name} | quad-blocks job {jid[:8]} ({verdict}) | agrees with golden on all {r[1]} checks |\n")
        print(f"ACCEPT {name}: {r[1]} checks agree ({verdict})")
    else:
        bad += 1
        print(f"REJECT {name}: {r[0]} of {r[1]} differ: {r[2][:160]}")
sys.exit(1 if bad else 0)
