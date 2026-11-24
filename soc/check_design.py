"""Structural check of a built design JSON: every endpoint exists with the right direction, every net has one driver and matching widths, every
block input is fed, and no top-level output is undriven.   python3 demos/quad-soc/check_design.py <design.json>"""
import json, sys
from collections import Counter

d = json.load(open(sys.argv[1]))
blk = {b["id"]: b for b in d["blocks"]}
tops = {t["id"]: t for t in d["topLevelPorts"]}


def port(e):
    if e["blockId"] is None:
        return tops.get(e["portId"])
    b = blk.get(e["blockId"])
    return None if b is None else next((p for p in b["ports"] if p["id"] == e["portId"]), None)


bad, drv, fed = [], Counter(), set()
for n in d["nets"]:
    dp = port(n["driver"])
    if dp is None:
        bad.append(("no such driver", n["name"], n["driver"])); continue
    isout = dp["direction"] in ("out", "output")
    if n["driver"]["blockId"] is None:
        isout = dp["direction"] in ("in", "input")      # a top-level input drives into the design
    if not isout:
        bad.append(("driver is not an output", n["name"], n["driver"]))
    drv[(n["driver"]["blockId"], n["driver"]["portId"])] += 1
    for s in n["sinks"]:
        sp = port(s)
        if sp is None:
            bad.append(("no such sink", n["name"], s)); continue
        if s["blockId"] is not None and sp["direction"] in ("out", "output"):
            bad.append(("sink is an output", n["name"], s))
        if sp["width"] != dp["width"]:
            bad.append(("width", n["name"], dp["width"], sp["width"], blk[s["blockId"]]["name"] if s["blockId"] else s["portId"]))
        fed.add((s["blockId"], s["portId"]))
multi = [k for k, c in drv.items() if c > 1]
unfed = [(b["name"], p["name"]) for b in d["blocks"] for p in b["ports"] if p["direction"] in ("in", "input") and (b["id"], p["id"]) not in fed]
top_undriven = [t["name"] for t in d["topLevelPorts"] if t["direction"] in ("out", "output") and (None, t["id"]) not in fed]
print(f"{len(d['blocks'])} blocks, {len(d['nets'])} nets")
print("problems:", len(bad)); [print("  ", b) for b in bad[:12]]
print("multi-driven:", multi[:6]); print("unfed inputs:", len(unfed)); [print("  ", u) for u in unfed[:20]]
print("undriven top outputs:", top_undriven)
sys.exit(1 if bad or multi or unfed or top_undriven else 0)
