"""The Wishbone bridge as a BARG design of its own (`simt-gpu-wb`): one block, `wb_bridge`, with its golden model.

    python3 demos/simt-gpu/wishbone/build_wb.py        # writes design.json

The bridge joins Caravel's Wishbone slave port (the management core is the master) to the GPU core's host bus. BARG generates and
checks the block like the core's 36; `caravel_gpu.v` (hand-written, a few wires) then puts it beside the core.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
import build as gpu  # noqa: E402

i, o, clocked, block, W = gpu.i, gpu.o, gpu.clocked, gpu.block, gpu.W

BRIDGE = block("b_wb_bridge", "wb_bridge", """
    Bridge from a Wishbone B4 classic slave port to a simple host bus, one word per transfer. Inputs: wb_cyc, wb_stb, wb_we,
    wb_sel (4 bits), wb_adr (32), wb_dat_i (32), and from the host bus host_rdata (32) and host_rvalid. Outputs: wb_ack, wb_dat_o
    (32), host_en, host_we, host_addr (32), host_wdata (32). Registers, all 0 after reset: state (2 bits: 0 IDLE, 1 REQ, 2
    WAIT, 3 DONE), we_r (1), addr_r (32), wdata_r (32), rdata_r (32).
    Outputs, all from registers (nothing depends on an input of the same cycle): host_en = (state == REQ); host_we =
    (state == REQ) & we_r; host_addr = addr_r; host_wdata = wdata_r; wb_ack = (state == DONE); wb_dat_o = rdata_r.
    On each rising edge: when rst is 1 every register becomes 0. Otherwise by state:
    IDLE: when wb_cyc & wb_stb: we_r = wb_we, wdata_r = wb_dat_i, rdata_r = 0 and the address is decoded as follows. The
    address is valid when wb_adr bits 31:20 equal 12'h300 and bits 1:0 are 0. The window is bits 19:16, with off = bits 15:0:
    window 0 (control registers) is mapped for every off, host address 32'h3000_0000 | off; window 1 (instruction memory) is
    mapped when off bits 15:11 are 0, host address = off bits 10:0 zero-extended to 32 bits; window 2 (global memory) is mapped
    when off bits 15:13 are 0, host address 32'h1000_0000 | off bits 12:0; window 3 (shared memory) is mapped when off bits
    15:12 are 0, host address 32'h2000_0000 | off bits 11:0; any other window is unmapped. If the address is valid and mapped,
    and (the access is a read, or wb_sel is 4'b1111), addr_r takes the host address and the state becomes REQ. Every other access
    (invalid, unmapped, or a write with wb_sel not 4'b1111) is dropped: addr_r keeps its value and the state becomes DONE
    (rdata_r is already 0). When wb_cyc & wb_stb is not 1 nothing happens.
    REQ: the state becomes DONE if we_r is 1 (a write), else WAIT (a read).
    WAIT: when host_rvalid is 1: rdata_r = host_rdata and the state becomes DONE; otherwise nothing changes.
    DONE: the state becomes IDLE.
    So a write takes 3 cycles from the cycle in which it is accepted to the cycle of wb_ack (IDLE, REQ, DONE), a read 4 when the
    host answers one cycle after the request (IDLE, REQ, WAIT, DONE), and wb_ack is high for exactly the cycle in state DONE.
""", clocked(i("wb_cyc", 1, "valid"), i("wb_stb", 1, "valid"), i("wb_we", 1, "control"), i("wb_sel", 4, "control"),
             i("wb_adr", W, "addr"), i("wb_dat_i", W, "data"), i("host_rdata", W, "data"), i("host_rvalid", 1, "valid"),
             o("wb_ack", 1, "control"), o("wb_dat_o", W, "data"), o("host_en", 1, "valid"), o("host_we", 1, "control"),
             o("host_addr", W, "addr"), o("host_wdata", W, "data")), reset_style="sync", latency=1)


def design() -> dict:
    nets, top = [], []
    for p in BRIDGE["ports"]:
        name, width, direction = p["name"], p["width"], p["direction"]
        tid = f"t_{name}"
        top.append({"blockId": None, **gpu.port(tid, name, direction, width, p.get("role"))})
        driver, sink = ({"blockId": None, "portId": tid}, {"blockId": "b_wb_bridge", "portId": p["id"]}) if direction == "in" else \
            ({"blockId": "b_wb_bridge", "portId": p["id"]}, {"blockId": None, "portId": tid})
        nets.append({"id": f"n_{len(nets) + 1:03d}", "name": name, "width": width, "driver": driver, "sinks": [sink],
                     "kind": "bus" if width > 1 else "wire", "pipelineStage": 0})
    return {"id": "simt-gpu-wb", "name": "Wishbone bridge for the SIMT GPU (Caravel user port to the host bus)", "version": 1,
            "createdAt": "2026-10-26T00:00:00.000Z", "blocks": [BRIDGE], "nets": nets, "topLevelPorts": top,
            "constraintGroups": [], "constraints": [], "referenceMaterial": []}


if __name__ == "__main__":
    d = design()
    (HERE / "design.json").write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    print(f"{HERE / 'design.json'}: 1 block, {len(d['nets'])} nets, {len(d['topLevelPorts'])} top-level ports")
