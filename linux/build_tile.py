"""The single-core SoC tile (`soc1`): the S-mode core (design-core.json) with its memory system, built into one BARG design.

    python3 demos/linux-soc/build_tile.py        # writes demos/linux-soc/design-soc1.json and copies.json

Around the core:
  * three TLBs (instruction low word, instruction high word, data) and the page-table walker, all on the free clock;
  * one RAM (`ram_main`, the curated barg_ram: 2^22 words = 16 MB, four read ports: data, fetch low, fetch high, walker);
  * the sized load (rload) and the byte lanes of a store (wlane), with the word address blocks and pack4/unpack4 between them;
  * the device side of the stage-4 SoC: region decoder, bus strobes, the CLINT (one hart), the 16550 UART, the reservation (amo_rsv)
    and the device read mux; the PLIC is not in this tile (its read data and meip are tile inputs);
  * the core's clock is gated by run and not mmu_stall (en_and, core_gate): the core waits while the walker walks.
Top-level inputs: clk (free), rst, run, grant, clear, hartid, mtime, ext_meip, plic_rdata, uart_rx_valid, uart_rx_data.
Top-level outputs: req, ptw_req, uart_irq, uart_tx_valid, uart_tx_data, plic_we, plic_re.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "quad-soc"))
import blocks as B  # noqa: E402
import build_quad as BQ  # noqa: E402

W = 32


def ep(b, p):
    return {"blockId": b, "portId": p}


def top(p):
    return {"blockId": None, "portId": f"t_{p}"}


def copy_as(blk, name, bid):
    c = copy.deepcopy(blk)
    c["id"], c["name"], c["moduleName"] = bid, name, name
    return c


def ram_main():
    """The curated RAM: 2^22 words, four read ports (catalogue kind 'ram', params DEPTH_W 22, READ_PORTS 4)."""
    ports = [("clk", "in", 1, "clock"), ("we", "in", 1, "control"), ("be", "in", 4, "control"), ("waddr", "in", 22, "addr"),
             ("wdata", "in", 32, "data"), ("raddr", "in", 88, "addr"), ("rdata", "out", 128, "data")]
    return {"id": "b_ram_main", "name": "ram_main", "tier": "T3", "provenance": "curated", "moduleName": "ram_main",
            "description": "16 MB RAM (curated barg_ram: 2^22 words, four read ports: data, fetch low word, fetch high word, walker)",
            "ports": [{"id": f"p_{n}", "name": n, "direction": d, "width": w, "role": r} for n, d, w, r in ports],
            "clockDomain": "main", "resetStyle": "none", "latencyCycles": 0, "verified": True,
            "ip": {"kind": "ram", "params": {"DEPTH_W": 22, "READ_PORTS": 4}}}


def stage4(name):
    d = json.loads((ROOT / "demos" / "nuttx-soc" / "design-a-16mb.json").read_text())
    return copy.deepcopy(next(b for b in d["blocks"] if b["name"] == name))


def design():
    core = json.loads((HERE / "design-core.json").read_text())
    core_ids = {b["id"] for b in core["blocks"]}
    new_blocks = []
    copies = {}
    for n in ("tlb_ilo", "tlb_ihi", "tlb_d"):
        new_blocks.append(copy_as(B.TLB, n, f"b_{n}")); copies[n] = "tlb"
    for n in ("wa_flo", "wa_fhi", "wa_ptw", "wa_data", "wa_write"):
        new_blocks.append(copy_as(B.WORD_ADDR, n, f"b_{n}")); copies[n] = "word_addr"
    new_blocks += [B.PTW, B.WLANE, B.RLOAD, B.PACK4, B.UNPACK4]
    new_blocks.append(copy.deepcopy(BQ.CORE_GATE))
    new_blocks.append(copy.deepcopy(next(b for b in B.BLOCKS if b["name"] == "en_and")))
    # the walker's clear: the core's redirect counts only on a cycle the core advances (redirect AND NOT mmu_stall)
    new_blocks.append(copy.deepcopy(next(b for b in B.BLOCKS if b["name"] == "en_and")) | {"id": "b_en_and_clr", "name": "en_and_clr", "moduleName": "en_and_clr"})
    new_blocks.append(ram_main())
    copies["en_and_clr"] = "en_and"
    dev = [stage4(n) for n in ("region_decode", "bus_ctl", "io_mux", "clint", "clint_decode", "uart16550", "amo_rsv")]
    for b in new_blocks + dev:
        if b["id"] in core_ids:
            raise SystemExit(f"block id clash: {b['id']}")
    blocks_all = core["blocks"] + dev + new_blocks

    nets = []

    def net(name, width, driver, sinks):
        nets.append({"id": f"n_t{len(nets) + 1:03d}", "name": name, "width": width, "driver": driver, "sinks": list(sinks),
                     "kind": "bus" if width > 1 else "wire", "pipelineStage": 0})

    # --- the core's own nets, with its top-level ports replaced by the tile's blocks
    IN = {  # core input -> the tile's driver
        "memory_read": ep("b_rload", "p_rdata"), "ext_msip": ep("b_clint", "p_msip"), "ext_mtip": ep("b_clint", "p_mtip"),
        "sel_ram": ep("b_region_decode", "p_sel_ram"), "ram_we": ep("b_bus_ctl", "p_ram_we"), "is_io": ep("b_region_decode", "p_is_io"),
        "io_raw": ep("b_io_mux", "p_y"), "rsv_valid": ep("b_amo_rsv", "p_rsv_valid"), "rsv_addr": ep("b_amo_rsv", "p_rsv_addr"),
        "inst_lo": ep("b_unpack4", "p_w1"), "inst_hi": ep("b_unpack4", "p_w2"),
        "tlb_ilo_hit": ep("b_tlb_ilo", "p_hit"), "tlb_ilo_ppa": ep("b_tlb_ilo", "p_ppa"), "tlb_ilo_flags": ep("b_tlb_ilo", "p_flags"),
        "tlb_ihi_hit": ep("b_tlb_ihi", "p_hit"), "tlb_ihi_ppa": ep("b_tlb_ihi", "p_ppa"), "tlb_ihi_flags": ep("b_tlb_ihi", "p_flags"),
        "tlb_d_hit": ep("b_tlb_d", "p_hit"), "tlb_d_ppa": ep("b_tlb_d", "p_ppa"), "tlb_d_flags": ep("b_tlb_d", "p_flags"),
        "ptw_busy": ep("b_ptw", "p_busy"), "ptw_fault": ep("b_ptw", "p_fault"), "ptw_fault_access": ep("b_ptw", "p_fault_access"),
        "ptw_fault_vpn": ep("b_ptw", "p_fault_vpn"),
    }
    KEEP_IN = {"hartid", "ext_meip", "mtime", "rst"}          # stay top-level inputs of the tile
    OUT = {  # core output -> the tile's sinks
        "mem_alu_y": [ep("b_wa_data", "p_addr"), ep("b_wlane", "p_addr"), ep("b_rload", "p_addr"), ep("b_region_decode", "p_addr"),
                      ep("b_clint_decode", "p_addr"), ep("b_uart", "p_addr"), ep("b_amo_rsv", "p_addr"), ep("b_wa_write", "p_addr")],
        "mem_store_data": [ep("b_clint", "p_wdata"), ep("b_uart", "p_wdata")],
        "mem_memtype": [ep("b_wlane", "p_memtype"), ep("b_rload", "p_memtype")],
        "mem_memsrc": [ep("b_bus_ctl", "p_memsrc")], "mem_valid": [ep("b_bus_ctl", "p_valid")], "mem_xcpt": [ep("b_bus_ctl", "p_xcpt")],
        "mem_write": [ep("b_bus_ctl", "p_memwrite")], "mem_kill": [ep("b_bus_ctl", "p_kill")],
        "dmem_we": [ep("b_ram_main", "p_we")], "dmem_wdata": [ep("b_wlane", "p_wdata")],
        "rsv_set": [ep("b_amo_rsv", "p_set")], "rsv_clr": [ep("b_amo_rsv", "p_clear")],
        "satp_ppn": [ep("b_ptw", "p_satp_ppn")],
        "sfence": [ep("b_tlb_ilo", "p_flush"), ep("b_tlb_ihi", "p_flush"), ep("b_tlb_d", "p_flush")],
        "fetch_pa_lo": [ep("b_wa_flo", "p_addr")], "fetch_pa_hi": [ep("b_wa_fhi", "p_addr")],
        "va_ilo": [ep("b_tlb_ilo", "p_va")], "va_ihi": [ep("b_tlb_ihi", "p_va")], "va_d": [ep("b_tlb_d", "p_va")],
        "walk_va": [ep("b_ptw", "p_vaddr")], "walk_start": [ep("b_ptw", "p_start")], "mmu_stall": [ep("b_en_and", "p_stall"), ep("b_en_and_clr", "p_stall")],
        "req": [top("req")],
        "wb_redirect": [ep("b_en_and_clr", "p_run")],
    }
    for n in core["nets"]:
        n = copy.deepcopy(n)
        drv = n["driver"]
        if drv["blockId"] is None:
            p = drv["portId"][2:]
            if p == "clk":
                n["driver"] = ep("b_core_gate", "p_gclk")
            elif p in IN:
                n["driver"] = IN[p]
            elif p in KEEP_IN:
                pass
            else:
                raise SystemExit(f"core input {p} has no tile driver")
        sinks = []
        for s in n["sinks"]:
            if s["blockId"] is None:
                p = s["portId"][2:]
                if p in OUT:
                    sinks += OUT[p]
                    continue
                raise SystemExit(f"core output {p} has no tile sink")
            sinks.append(s)
        n["sinks"] = sinks
        nets.append(n)
    # --- the tile's own nets
    net("clk_free", 1, top("clk"), [ep("b_tlb_ilo", "p_clk"), ep("b_tlb_ihi", "p_clk"), ep("b_tlb_d", "p_clk"), ep("b_ptw", "p_clk"),
                                    ep("b_ram_main", "p_clk"), ep("b_core_gate", "p_clk"), ep("b_en_and", "p_run") if False else ep("b_clint", "p_clk"),
                                    ep("b_uart", "p_clk"), ep("b_amo_rsv", "p_clk")])
    # the reset is one top-level input: all its sinks go on the core's own reset net (the emitter gives a top input one net)
    rst_net = next(n for n in nets if n["driver"] == top("rst"))
    rst_net["sinks"] += [ep("b_tlb_ilo", "p_rst"), ep("b_tlb_ihi", "p_rst"), ep("b_tlb_d", "p_rst"), ep("b_ptw", "p_rst"),
                         ep("b_core_gate", "p_rst"), ep("b_clint", "p_rst"), ep("b_uart", "p_rst"), ep("b_amo_rsv", "p_rst")]
    net("run", 1, top("run"), [ep("b_en_and", "p_run")])
    net("clr_en", 1, ep("b_en_and_clr", "p_en"), [ep("b_ptw", "p_clear")])
    net("grant", 1, top("grant"), [ep("b_ptw", "p_grant")])
    net("core_en", 1, ep("b_en_and", "p_en"), [ep("b_core_gate", "p_en")])
    net("ptw_rdata", W, ep("b_unpack4", "p_w3"), [ep("b_ptw", "p_rdata")])
    net("ptw_addr", W, ep("b_ptw", "p_addr"), [ep("b_wa_ptw", "p_addr")])
    net("ptw_req", 1, ep("b_ptw", "p_req"), [top("ptw_req")])
    net("pw_fill", 1, ep("b_ptw", "p_fill"), [ep("b_tlb_ilo", "p_fill"), ep("b_tlb_ihi", "p_fill"), ep("b_tlb_d", "p_fill")])
    net("pw_fill_vpn", 20, ep("b_ptw", "p_fill_vpn"), [ep("b_tlb_ilo", "p_fill_vpn"), ep("b_tlb_ihi", "p_fill_vpn"), ep("b_tlb_d", "p_fill_vpn")])
    net("pw_fill_ppn", 22, ep("b_ptw", "p_fill_ppn"), [ep("b_tlb_ilo", "p_fill_ppn"), ep("b_tlb_ihi", "p_fill_ppn"), ep("b_tlb_d", "p_fill_ppn")])
    net("pw_fill_mega", 1, ep("b_ptw", "p_fill_mega"), [ep("b_tlb_ilo", "p_fill_mega"), ep("b_tlb_ihi", "p_fill_mega"), ep("b_tlb_d", "p_fill_mega")])
    net("pw_fill_flags", 8, ep("b_ptw", "p_fill_flags"), [ep("b_tlb_ilo", "p_fill_flags"), ep("b_tlb_ihi", "p_fill_flags"), ep("b_tlb_d", "p_fill_flags")])
    net("wa_data_out", 22, ep("b_wa_data", "p_word"), [ep("b_pack4", "p_a0")])
    net("wa_flo_out", 22, ep("b_wa_flo", "p_word"), [ep("b_pack4", "p_a1")])
    net("wa_fhi_out", 22, ep("b_wa_fhi", "p_word"), [ep("b_pack4", "p_a2")])
    net("wa_ptw_out", 22, ep("b_wa_ptw", "p_word"), [ep("b_pack4", "p_a3")])
    net("wa_write_out", 22, ep("b_wa_write", "p_word"), [ep("b_ram_main", "p_waddr")])
    net("ram_raddr", 88, ep("b_pack4", "p_bus88"), [ep("b_ram_main", "p_raddr")])
    net("ram_rdata", 128, ep("b_ram_main", "p_rdata"), [ep("b_unpack4", "p_bus128")])
    net("ram_be", 4, ep("b_wlane", "p_be"), [ep("b_ram_main", "p_be")])
    net("ram_wdata", W, ep("b_wlane", "p_data"), [ep("b_ram_main", "p_wdata")])
    net("word0", W, ep("b_unpack4", "p_w0"), [ep("b_rload", "p_word")])
    net("clint_rdata", W, ep("b_clint", "p_rdata"), [ep("b_io_mux", "p_clint_rdata")])
    net("uart_rdata", W, ep("b_uart", "p_rdata"), [ep("b_io_mux", "p_uart_rdata")])
    net("plic_rdata", W, top("plic_rdata"), [ep("b_io_mux", "p_plic_rdata")])
    net("clint_idx", 3, ep("b_clint_decode", "p_idx"), [ep("b_clint", "p_idx")])
    net("clint_we", 1, ep("b_bus_ctl", "p_clint_we"), [ep("b_clint", "p_we")])
    net("uart_we", 1, ep("b_bus_ctl", "p_uart_we"), [ep("b_uart", "p_we")])
    net("uart_re", 1, ep("b_bus_ctl", "p_uart_re"), [ep("b_uart", "p_re")])
    net("uart_rx_valid", 1, top("uart_rx_valid"), [ep("b_uart", "p_rx_valid")])
    net("uart_rx_data", 8, top("uart_rx_data"), [ep("b_uart", "p_rx_data")])
    net("uart_irq", 1, ep("b_uart", "p_irq"), [top("uart_irq")])
    net("uart_tx_valid", 1, ep("b_uart", "p_tx_valid"), [top("uart_tx_valid")])
    net("uart_tx_data", 8, ep("b_uart", "p_tx_data"), [top("uart_tx_data")])
    net("plic_we", 1, ep("b_bus_ctl", "p_plic_we"), [top("plic_we")])
    net("plic_re", 1, ep("b_bus_ctl", "p_plic_re"), [top("plic_re")])
    net("sel_clint", 1, ep("b_region_decode", "p_sel_clint"), [ep("b_bus_ctl", "p_sel_clint"), ep("b_io_mux", "p_sel_clint")])
    net("sel_plic", 1, ep("b_region_decode", "p_sel_plic"), [ep("b_bus_ctl", "p_sel_plic"), ep("b_io_mux", "p_sel_plic")])
    net("sel_uart", 1, ep("b_region_decode", "p_sel_uart"), [ep("b_bus_ctl", "p_sel_uart"), ep("b_io_mux", "p_sel_uart")])
    net("sel_ram_bus", 1, ep("b_region_decode", "p_sel_ram"), [ep("b_bus_ctl", "p_sel_ram")])
    # the top-level ports of the tile
    tops = [{"id": "t_clk", "name": "clk", "direction": "in", "width": 1, "role": "clock", "blockId": None},
            {"id": "t_rst", "name": "rst", "direction": "in", "width": 1, "role": "reset", "blockId": None}]
    for name, d, w, r in [("run", "in", 1, "control"), ("grant", "in", 1, "control"), 
                          ("hartid", "in", 2, "control"), ("mtime", "in", 64, "data"), ("ext_meip", "in", 1, "control"),
                          ("plic_rdata", "in", 32, "data"), ("uart_rx_valid", "in", 1, "valid"), ("uart_rx_data", "in", 8, "data"),
                          ("req", "out", 1, "control"), ("ptw_req", "out", 1, "control"), ("uart_irq", "out", 1, "control"),
                          ("uart_tx_valid", "out", 1, "valid"), ("uart_tx_data", "out", 8, "data"), ("plic_we", "out", 1, "control"),
                          ("plic_re", "out", 1, "control")]:
        tops.append({"id": f"t_{name}", "name": name, "direction": d, "width": w, "role": r, "blockId": None})
    # the core's own top-level ports that the tile keeps (hartid, ext_meip, mtime, rst) are the tile's ports
    # the emitter drives a block output onto one wire only: every output port drives exactly one net (sinks merged)
    by_driver = {}
    for n in nets:
        key = (n["driver"]["blockId"], n["driver"]["portId"])
        if key in by_driver:
            first = by_driver[key]
            first["sinks"] += [x for x in n["sinks"] if x not in first["sinks"]]
            n["_merged"] = True
        else:
            by_driver[key] = n
    nets = [n for n in nets if not n.get("_merged")]
    return {"id": "soc1", "name": "Single-core SoC tile: S-mode core, Sv32 MMU, 16 MB RAM, CLINT, UART",
            "version": 1, "createdAt": "2026-11-20T00:00:00.000Z", "blocks": blocks_all, "nets": nets, "topLevelPorts": tops,
            "constraintGroups": [], "constraints": []}, copies


if __name__ == "__main__":
    d, copies = design()
    (HERE / "design-soc1.json").write_text(json.dumps(d, indent=1))
    (HERE / "copies.json").write_text(json.dumps(copies, indent=1))
    print(f"{len(d['blocks'])} blocks, {len(d['nets'])} nets, {len(d['topLevelPorts'])} top-level ports")
