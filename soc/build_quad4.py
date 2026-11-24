"""The quad-core SoC (`quad4`): four copies of the single-core tile's core and memory side, one shared bus, one device side.

    python3 demos/quad-soc/build_quad4.py        # writes demos/quad-soc/design-quad4.json and copies4.json

Per hart k (names c<k>_*): the core (demos/linux-soc/design-core.json), three TLBs, the walker, its read-port glue (word addresses,
rload), its clock gate (en_and, core_gate), its clear gate (en_and_clr: the core's redirect counts on a cycle it advances), its
reservation (rsv_gate, amo_rsv).
Shared: bus_arb (one grant per cycle; a core that asks for the bus and is not granted stalls), bus_mux4 (the granted core's bus signals),
the write path (wa_write, wlane, RAM write port), the device side (region_decode, bus_ctl, clint_decode4, clint4, uart16550, io_mux),
hart_cfg (hart ids, meip), pack16/unpack16 and the RAM (16 read ports: four per hart, and one write port).
Top-level inputs: clk, rst, rx_valid, rx_data, ext_s2, ext_s3 (PLIC sources 2 and 3), meip (spare, feeds hart_cfg only). Outputs: uart_irq, uart_tx_valid, uart_tx_data.
The PLIC (plic4) takes the UART interrupt as source 1; its four contexts are the harts' external interrupts.
"""
from __future__ import annotations

import copy, json, re, sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "linux-soc"))
sys.path.insert(0, str(HERE.parent / "gpu-soc"))
sys.path.insert(0, str(HERE))
import blocks as B  # noqa: E402
from build_gpu_soc import block, i, o, port  # noqa: E402
import build_quad as BQ  # noqa: E402
import periphblocks as PB  # noqa: E402
import importlib.util as _ilu  # noqa: E402
_sf = _ilu.spec_from_file_location("socfinal_blocks", HERE.parent / "soc-final" / "blocks.py")
SF = _ilu.module_from_spec(_sf)
_sf.loader.exec_module(SF)  # region_decode, bus_ctl, io_mux of the final memory map (64 MB RAM, 32 MB GPU window, peripheral window)
CLUSTER = json.loads((ROOT / "demos" / "gpu-cluster" / "design.json").read_text())

NC, W = 4, 32
GPU = "--no-gpu" not in sys.argv  # --no-gpu: the CPU-only build (the GPU window reads from the pin gpu_rdata); about 4x faster to simulate, for the Linux boot
BP = "--bp" in sys.argv  # --bp: cores with the gshare branch predictor
FP = "--fp" in sys.argv  # --fp: cores with the F and D extensions (demos/linux-soc/design-core-fp.json)
PLIC = "--no-plic" not in sys.argv  # --no-plic: staging build without the interrupt controller (the cores take meip from the spare pin)
PORTS = {"clk": None}


TOPS = [("clk", "in", 1, "clock"), ("rst", "in", 1, "reset"), ("rx_valid", "in", 1, "control"), ("rx_data", "in", 8, "data"),
        ("plic_rdata", "in", 32, "data"), ("ext_s2", "in", 1, "control"), ("ext_s3", "in", 1, "control"), ("meip", "in", 1, "control"),
        ("uart_irq", "out", 1, "control"), ("uart_tx_valid", "out", 1, "control"), ("uart_tx_data", "out", 8, "data"),
        ("periph_rdata", "in", 32, "data"), ("periph_we", "out", 1, "control"), ("periph_re", "out", 1, "control"),
        ("bus_addr", "out", 32, "addr"), ("bus_wdata", "out", 32, "data"),
        ("gpu_running", "out", 1, "control"), ("gpu_done", "out", 1, "control"), ("gpu_error", "out", 1, "control"),
        ("gpu_diverged", "out", 1, "control"), ("gpu_hsync", "out", 1, "control"), ("gpu_vsync", "out", 1, "control"),
        ("gpu_de", "out", 1, "control"), ("gpu_rgb", "out", 16, "data"), ("gpu_rdata", "in", 32, "data")]


def ep(b, p):
    return {"blockId": b, "portId": p}


def top(p, direction=None):
    return {"blockId": None, "portId": f"t_{p}"}


ORIG_ID = {"uart16550": "uart", "region_decode": "region_decode", "bus_ctl": "bus_ctl", "io_mux": "io_mux"}  # stage-4 RTL is keyed by these


def bid(name, k=None):
    if k is None:
        return f"b_{ORIG_ID.get(name, name)}"
    return f"b_c{k}_{name}"


def copy_as(spec, name, blockid):
    c = copy.deepcopy(spec)
    c["id"], c["name"], c["moduleName"] = blockid, name, name
    return c


def stage4(name):
    d = json.loads((ROOT / "demos" / "nuttx-soc" / "design-a-16mb.json").read_text())
    return copy.deepcopy(next(b for b in d["blocks"] if b["name"] == name))


def spec(name):
    return copy.deepcopy(next(b for b in B.BLOCKS if b["name"] == name))


def ram16():
    """The curated RAM: 2^24 words (64 MB), sixteen read ports (four per hart), one write port."""
    ports = [("clk", "in", 1, "clock"), ("we", "in", 1, "control"), ("be", "in", 4, "control"), ("waddr", "in", 24, "addr"),
             ("wdata", "in", 32, "data"), ("raddr", "in", 384, "addr"), ("rdata", "out", 512, "data")]
    return {"id": "b_ram_main", "name": "ram_main", "tier": "T3", "provenance": "curated", "moduleName": "ram_main",
            "description": "64 MB RAM (curated barg_ram: 2^24 words, sixteen read ports: four per hart, one write port)",
            "ports": [{"id": f"p_{n}", "name": n, "direction": d, "width": w, "role": r} for n, d, w, r in ports],
            "clockDomain": "main", "resetStyle": "none", "latencyCycles": 0, "verified": True,
            "ip": {"kind": "ram", "params": {"DEPTH_W": 24, "READ_PORTS": 16}}}


def design():
    core = json.loads((ROOT / "demos" / "linux-soc" / ("design-core" + ("-fp" if FP else "") + ("-bp" if BP else "") + ".json")).read_text())
    core_ids = {b["id"] for b in core["blocks"]}
    copies = {}
    blocks_all, nets = [], []

    origids = {}

    def add_block(b, base, origid=None, k=None):
        blocks_all.append(b)
        copies[b["name"]] = base
        origids[b["name"]] = origid or b["id"]

    def net(name, width, driver, sinks):
        nets.append({"id": f"n_q{len(nets) + 1:04d}", "name": name, "width": width, "driver": driver, "sinks": list(sinks),
                     "kind": "bus" if width > 1 else "wire", "pipelineStage": 0})

    # ------------------------------------------------------------------ the shared blocks
    shared = {
        "bus_arb": copy_as(BQ.BUS_ARB, "bus_arb", bid("bus_arb")),
        "bus_mux4": copy_as(BQ.BUS_MUX4, "bus_mux4", bid("bus_mux4")),
        "region_decode": copy_as(SF.REGION_DECODE, "region_decode", bid("region_decode")),
        "bus_ctl": copy_as(SF.BUS_CTL, "bus_ctl", bid("bus_ctl")),
        "clint_decode4": copy_as(BQ.CLINT_DECODE4, "clint_decode4", bid("clint_decode4")),
        "clint4": copy_as(BQ.CLINT4, "clint4", bid("clint4")),
        "uart16550": copy_as(PB.UART16550F, "uart16550", bid("uart16550")),   # the 16550 with a 16-byte receive FIFO (periphblocks.py)
        "io_mux": copy_as(SF.IO_MUX, "io_mux", bid("io_mux")),
        "hart_cfg": copy_as(BQ.HART_CFG, "hart_cfg", bid("hart_cfg")),
        **({"plic4": copy_as(BQ.PLIC4, "plic4", bid("plic4"))} if PLIC else {}),
        "wa_write": copy_as(BQ.WORD_ADDR24, "wa_write", bid("wa_write")),
        "wlane": copy_as(spec("wlane"), "wlane", bid("wlane")),
        "pack16": copy_as(BQ.PACK16W, "pack16", bid("pack16")),
        "unpack16": copy_as(spec("unpack16"), "unpack16", bid("unpack16")),
        "ram_main": ram16(),
    }
    base_of = {"bus_arb": "bus_arb", "bus_mux4": "bus_mux4", "region_decode": "region_decode", "bus_ctl": "bus_ctl",
               "clint_decode4": "clint_decode4", "clint4": "clint4", "uart16550": "uart16550", "io_mux": "io_mux",
               "hart_cfg": "hart_cfg", "plic4": "plic4", "wa_write": "word_addr24", "wlane": "wlane", "pack16": "pack16w", "unpack16": "unpack16",
               "ram_main": "ram_main"}
    origid = {"region_decode": "b_final_region_decode", "bus_ctl": "b_final_bus_ctl", "uart16550": "b_uart", "io_mux": "b_final_io_mux"}
    for n, b in shared.items():
        add_block(b, base_of[n], origid.get(n))

    # ------------------------------------------------------------------ the per-hart blocks
    per = {  # name -> (spec, base for the RTL, original id for stage-4 RTL or None)
        "tlb_ilo": (spec("tlb"), "tlb"), "tlb_ihi": (spec("tlb"), "tlb"), "tlb_d": (spec("tlb"), "tlb"),
        "ptw": (spec("ptw"), "ptw"),
        "wa_flo": (BQ.WORD_ADDR24, "word_addr24"), "wa_fhi": (BQ.WORD_ADDR24, "word_addr24"),
        "wa_ptw": (BQ.WORD_ADDR24, "word_addr24"), "wa_data": (BQ.WORD_ADDR24, "word_addr24"),
        "rload": (spec("rload"), "rload"),
        "en_and": (spec("en_and"), "en_and"), "en_and_clr": (spec("en_and"), "en_and"), "en_and_sf": (spec("en_and"), "en_and"), "en_and_rq": (spec("en_and"), "en_and"),
        "core_gate": (copy.deepcopy(BQ.CORE_GATE), "core_gate"),
        "rsv_gate": (copy.deepcopy(BQ.RSV_GATE), "rsv_gate"),
        "amo_rsv": (stage4("amo_rsv"), "amo_rsv"),
    }
    for k in range(NC):
        for n, (sp, base) in per.items():
            add_block(copy_as(sp, f"c{k}_{n}", bid(n, k)), base, "b_amo_rsv" if n == "amo_rsv" else None, k)
        # the hart's core: the core design's blocks, renamed with the hart's prefix
        for cb in core["blocks"]:
            c = copy.deepcopy(cb)
            c["id"] = f"b_c{k}_" + cb["id"][2:]
            c["name"] = f"c{k}_{cb['name']}"
            c["moduleName"] = f"c{k}_{cb['moduleName']}"
            base = re.sub(r"_(ilo|ihi|d)$", "", cb["name"]) if re.sub(r"_(ilo|ihi|d)$", "", cb["name"]) in ("pa_mux", "perm_check", "xfault") else cb["name"]
            add_block(c, base, cb["id"], k)

    # the GPU cluster (demos/gpu-cluster): its blocks as they are (the ten simt_gpu are IP blocks; `ip.js flatten` expands them)
    for cb in (CLUSTER["blocks"] if GPU else []):
        add_block(copy.deepcopy(cb), cb["name"], cb["id"])

    def C(k, bid_core):  # a core-internal block id of hart k
        return f"b_c{k}_" + bid_core[2:]

    # ------------------------------------------------------------------ each hart's core nets (the core's top-level nets)
    IN = {  # core input -> the driver (per hart)
        "memory_read": lambda k: ep(bid("rload", k), "p_rdata"),
        "ext_msip": lambda k: ep(bid("clint4"), f"p_msip{k}"),
        "ext_mtip": lambda k: ep(bid("clint4"), f"p_mtip{k}"),
        "ext_meip": lambda k: ep(bid("plic4"), f"p_meip{k}") if PLIC else ep(bid("hart_cfg"), f"p_meip{k}"),
        "hartid": lambda k: ep(bid("hart_cfg"), f"p_hartid{k}"),
        "sel_ram": lambda k: ep(bid("region_decode"), "p_sel_ram"),
        "ram_we": lambda k: ep(bid("bus_ctl"), "p_ram_we"),
        "is_io": lambda k: ep(bid("region_decode"), "p_is_io"),
        "io_raw": lambda k: ep(bid("io_mux"), "p_y"),
        "rsv_valid": lambda k: ep(bid("amo_rsv", k), "p_rsv_valid"),
        "rsv_addr": lambda k: ep(bid("amo_rsv", k), "p_rsv_addr"),
        "mtime": lambda k: ep(bid("clint4"), "p_mtime"),
        "inst_lo": lambda k: ep(bid("unpack16"), f"p_w{4 * k + 1}"),
        "inst_hi": lambda k: ep(bid("unpack16"), f"p_w{4 * k + 2}"),
        "tlb_ilo_hit": lambda k: ep(bid("tlb_ilo", k), "p_hit"), "tlb_ilo_ppa": lambda k: ep(bid("tlb_ilo", k), "p_ppa"),
        "tlb_ilo_flags": lambda k: ep(bid("tlb_ilo", k), "p_flags"),
        "tlb_ihi_hit": lambda k: ep(bid("tlb_ihi", k), "p_hit"), "tlb_ihi_ppa": lambda k: ep(bid("tlb_ihi", k), "p_ppa"),
        "tlb_ihi_flags": lambda k: ep(bid("tlb_ihi", k), "p_flags"),
        "tlb_d_hit": lambda k: ep(bid("tlb_d", k), "p_hit"), "tlb_d_ppa": lambda k: ep(bid("tlb_d", k), "p_ppa"),
        "tlb_d_flags": lambda k: ep(bid("tlb_d", k), "p_flags"),
        "ptw_busy": lambda k: ep(bid("ptw", k), "p_busy"), "ptw_fault": lambda k: ep(bid("ptw", k), "p_fault"),
        "ptw_fault_access": lambda k: ep(bid("ptw", k), "p_fault_access"),
        "ptw_fault_vpn": lambda k: ep(bid("ptw", k), "p_fault_vpn"),
    }
    OUT = {  # core output -> the sinks (per hart)
        "mem_alu_y": lambda k: [ep(bid("wa_data", k), "p_addr"), ep(bid("rload", k), "p_addr"), ep(bid("amo_rsv", k), "p_addr"),
                                ep(bid("bus_mux4"), f"p_addr{k}"), ep(bid("wa_data", k), "p_addr")][:4],
        "mem_store_data": lambda k: [ep(bid("bus_mux4"), f"p_store_data{k}")],
        "mem_memtype": lambda k: [ep(bid("rload", k), "p_memtype"), ep(bid("bus_mux4"), f"p_memtype{k}")],
        "mem_memsrc": lambda k: [ep(bid("bus_mux4"), f"p_memsrc{k}")],
        "mem_valid": lambda k: [ep(bid("bus_mux4"), f"p_valid{k}")],
        "mem_xcpt": lambda k: [ep(bid("bus_mux4"), f"p_xcpt{k}")],
        "mem_write": lambda k: [ep(bid("bus_mux4"), f"p_memwrite{k}")],
        "mem_kill": lambda k: [ep(bid("bus_mux4"), f"p_kill{k}")],
        "dmem_we": lambda k: [ep(bid("bus_mux4"), f"p_dmem_we{k}")],
        "dmem_wdata": lambda k: [ep(bid("bus_mux4"), f"p_dmem_wdata{k}")],
        "req": lambda k: [ep(bid("en_and_rq", k), "p_run")],   # the bus request counts only while the core is not held for a page walk (see below)
        "rsv_set": lambda k: [ep(bid("rsv_gate", k), "p_set_rsv")],
        "rsv_clr": lambda k: [ep(bid("rsv_gate", k), "p_clr_rsv")],
        "satp_ppn": lambda k: [ep(bid("ptw", k), "p_satp_ppn")],
        "sfence": lambda k: [ep(bid("en_and_sf", k), "p_run")],   # the flush counts on a cycle the core advances (see below)
        "fetch_pa_lo": lambda k: [ep(bid("wa_flo", k), "p_addr")],
        "fetch_pa_hi": lambda k: [ep(bid("wa_fhi", k), "p_addr")],
        "va_ilo": lambda k: [ep(bid("tlb_ilo", k), "p_va")], "va_ihi": lambda k: [ep(bid("tlb_ihi", k), "p_va")],
        "va_d": lambda k: [ep(bid("tlb_d", k), "p_va")],
        "walk_va": lambda k: [ep(bid("ptw", k), "p_vaddr")], "walk_start": lambda k: [ep(bid("ptw", k), "p_start")],
        "mmu_stall": lambda k: [ep(bid("en_and", k), "p_stall"), ep(bid("en_and_clr", k), "p_stall"), ep(bid("en_and_sf", k), "p_stall"), ep(bid("en_and_rq", k), "p_stall")],
        "wb_redirect": lambda k: [ep(bid("en_and_clr", k), "p_run")],
    }
    # every hart's core nets (driver -> sinks), with the hart's top-level ports mapped to the shared blocks
    links = []  # (driver endpoint or top key, [sink endpoints])
    for k in range(NC):
        for cb_net in core["nets"]:
            drv = cb_net["driver"]
            sinks = []
            if drv["blockId"] is None:
                p = drv["portId"][2:]
                if p == "clk":
                    driver = ep(bid("core_gate", k), "p_gclk")
                elif p == "rst":
                    driver = top("rst")
                elif p in IN:
                    driver = IN[p](k)
                else:
                    raise SystemExit(f"hart core input {p} unmapped")
            else:
                driver = ep(C(k, drv["blockId"]), drv["portId"])
            for sk in cb_net["sinks"]:
                if sk["blockId"] is None:
                    p = sk["portId"][2:]
                    if p in OUT:
                        sinks += OUT[p](k)
                    elif p in ("rst", "clk"):
                        pass
                    else:
                        raise SystemExit(f"hart core output {p} unmapped")
                else:
                    sinks.append(ep(C(k, sk["blockId"]), sk["portId"]))
            links.append((driver, sinks))
    cl_in = {"t_clk": top("clk"), "t_rst": top("rst"), "t_gpu_we": ep(bid("bus_ctl"), "p_gpu_we"), "t_gpu_re": ep(bid("bus_ctl"), "p_gpu_re"),
             "t_addr": ep(bid("bus_mux4"), "p_addr"), "t_wdata": ep(bid("bus_mux4"), "p_store_data"),
             "t_memtype": ep(bid("bus_mux4"), "p_memtype")}
    if not GPU:
        links.append((top("gpu_rdata"), [ep(bid("io_mux"), "p_gpu_rdata")]))
    for cb_net in (CLUSTER["nets"] if GPU else []):
        drv = cb_net["driver"]
        driver = drv if drv["blockId"] is not None else cl_in[drv["portId"]]
        sinks = []
        for sk in cb_net["sinks"]:
            if sk["blockId"] is None:
                sinks.append(ep(bid("io_mux"), "p_gpu_rdata") if sk["portId"] == "t_rdata" else top(sk["portId"][2:]))
            else:
                sinks.append(sk)
        links.append((driver, sinks))
    # the shared wiring: the reset and clock nets, the arbiter and the granted bus, the write path, the device side and the RAM
    links.append((top("rst"), [ep(bid("bus_arb"), "p_rst"), ep(bid("clint4"), "p_rst"), ep(bid("uart16550"), "p_rst"),
                               ep(bid("hart_cfg"), "p_rst") if False else None]))
    links[-1] = (top("rst"), [s for s in links[-1][1] if s])
    links.append((top("clk"), [ep(bid("bus_arb"), "p_clk"), ep(bid("clint4"), "p_clk"), ep(bid("uart16550"), "p_clk"), ep(bid("ram_main"), "p_clk")]))
    links.append((top("meip"), [ep(bid("hart_cfg"), "p_meip")]))
    links.append((ep(bid("plic4"), "p_rdata") if PLIC else top("plic_rdata"), [ep(bid("io_mux"), "p_plic_rdata")]))
    links.append((top("ext_s2"), [ep(bid("plic4"), "p_s2")]))
    links.append((top("ext_s3"), [ep(bid("plic4"), "p_s3")]))
    links.append((top("rx_valid"), [ep(bid("uart16550"), "p_rx_valid")]))
    links.append((top("rx_data"), [ep(bid("uart16550"), "p_rx_data")]))
    for k in range(NC):
        links.append((ep(bid("bus_arb"), f"p_grant{k}"), [ep(bid("bus_mux4"), f"p_grant{k}"), ep(bid("rsv_gate", k), "p_self_grant")]))
        links.append((ep(bid("bus_arb"), f"p_run{k}"), [ep(bid("en_and", k), "p_run")]))
        links.append((ep(bid("en_and", k), "p_en"), [ep(bid("core_gate", k), "p_en")]))
        links.append((ep(bid("en_and_clr", k), "p_en"), [ep(bid("ptw", k), "p_clear")]))
        # sfence.vma flushes the TLBs only in a cycle the core advances: while the core waits for a page walk the instruction stays in write-back,
        # and a flush held every cycle would wipe each entry the walker fills (found by the FP Linux kernel, whose code patching hit it)
        # the core's bus request is held off while it waits for a page walk: its clock is gated then, so the instruction in the memory stage stays
        # put, and a granted request would repeat every cycle. A store repeats harmlessly, an atomic does not (amoadd applied once per stalled cycle,
        # found as a Linux file write-count that drifted positive: "Text file busy") and a device read with a side effect (UART FIFO pop) would repeat too
        links.append((ep(bid("en_and_rq", k), "p_en"), [ep(bid("bus_arb"), f"p_req{k}")]))
        links.append((ep(bid("en_and_sf", k), "p_en"), [ep(bid("tlb_ilo", k), "p_flush"), ep(bid("tlb_ihi", k), "p_flush"), ep(bid("tlb_d", k), "p_flush")]))
        # the walker reads its page tables through the hart's own port (port 4k+3), and the hart's fetch and data words
        # the walker reads through the hart's own RAM port, so it needs no turn on the bus: run<k> (1 while the hart is not asking for
        # the bus, or has it) lets it walk whenever the core is not waiting; grant<k> would stay 0 for a walk the core did not request
        links.append((ep(bid("bus_arb"), f"p_run{k}"), [ep(bid("ptw", k), "p_grant")]))
        links.append((ep(bid("ptw", k), "p_addr"), [ep(bid("wa_ptw", k), "p_addr")]))
        links.append((ep(bid("wa_data", k), "p_word"), [ep(bid("pack16"), f"p_a{4 * k}")]))
        links.append((ep(bid("wa_flo", k), "p_word"), [ep(bid("pack16"), f"p_a{4 * k + 1}")]))
        links.append((ep(bid("wa_fhi", k), "p_word"), [ep(bid("pack16"), f"p_a{4 * k + 2}")]))
        links.append((ep(bid("wa_ptw", k), "p_word"), [ep(bid("pack16"), f"p_a{4 * k + 3}")]))
        links.append((ep(bid("unpack16"), f"p_w{4 * k}"), [ep(bid("rload", k), "p_word")]))
        links.append((ep(bid("unpack16"), f"p_w{4 * k + 3}"), [ep(bid("ptw", k), "p_rdata")]))
        links.append((ep(bid("amo_rsv", k), "p_rsv_valid"), [ep(bid("rsv_gate", k), "p_rsv_valid")]))
        links.append((ep(bid("amo_rsv", k), "p_rsv_addr"), [ep(bid("rsv_gate", k), "p_rsv_addr")]))
        links.append((ep(bid("rsv_gate", k), "p_set"), [ep(bid("amo_rsv", k), "p_set")]))
        links.append((ep(bid("rsv_gate", k), "p_clear"), [ep(bid("amo_rsv", k), "p_clear")]))
        for t in ("tlb_ilo", "tlb_ihi", "tlb_d"):
            for sig in ("fill", "fill_vpn", "fill_ppn", "fill_mega", "fill_flags"):
                links.append((ep(bid("ptw", k), f"p_{sig}"), [ep(bid(t, k), f"p_{sig}")]))
        for pn in ("ptw_fault", "ptw_fault_access", "ptw_busy"):
            pass
    # the granted bus (the RAM write path, the device side)
    for sig, sinks in (
        ("addr", [ep(bid("region_decode"), "p_addr"), ep(bid("clint_decode4"), "p_addr"), ep(bid("uart16550"), "p_addr"), ep(bid("plic4"), "p_addr"), top("bus_addr"),
                  ep(bid("wa_write"), "p_addr"), ep(bid("wlane"), "p_addr")] + [ep(bid("rsv_gate", k), "p_addr") for k in range(NC)]),
        ("store_data", [ep(bid("clint4"), "p_wdata"), ep(bid("uart16550"), "p_wdata"), ep(bid("plic4"), "p_wdata"), top("bus_wdata")]),
        ("memtype", [ep(bid("wlane"), "p_memtype")]),
        ("memsrc", [ep(bid("bus_ctl"), "p_memsrc")]),
        ("valid", [ep(bid("bus_ctl"), "p_valid")]),
        ("xcpt", [ep(bid("bus_ctl"), "p_xcpt")]),
        ("memwrite", [ep(bid("bus_ctl"), "p_memwrite")]),
        ("kill", [ep(bid("bus_ctl"), "p_kill")]),
        ("dmem_we", [ep(bid("ram_main"), "p_we")] + [ep(bid("rsv_gate", k), "p_snoop_we") for k in range(NC)]),
        ("dmem_wdata", [ep(bid("wlane"), "p_wdata")]),
    ):
        links.append((ep(bid("bus_mux4"), f"p_{sig}"), sinks))
    links += [
        (ep(bid("wa_write"), "p_word"), [ep(bid("ram_main"), "p_waddr")]),
        (ep(bid("wlane"), "p_be"), [ep(bid("ram_main"), "p_be")]),
        (ep(bid("wlane"), "p_data"), [ep(bid("ram_main"), "p_wdata")]),
        (ep(bid("pack16"), "p_bus384"), [ep(bid("ram_main"), "p_raddr")]),
        (ep(bid("ram_main"), "p_rdata"), [ep(bid("unpack16"), "p_bus512")]),
        (ep(bid("region_decode"), "p_sel_clint"), [ep(bid("bus_ctl"), "p_sel_clint"), ep(bid("io_mux"), "p_sel_clint")]),
        (ep(bid("region_decode"), "p_sel_plic"), [ep(bid("bus_ctl"), "p_sel_plic"), ep(bid("io_mux"), "p_sel_plic")]),
        (ep(bid("region_decode"), "p_sel_uart"), [ep(bid("bus_ctl"), "p_sel_uart"), ep(bid("io_mux"), "p_sel_uart")]),
        (ep(bid("region_decode"), "p_sel_periph"), [ep(bid("bus_ctl"), "p_sel_periph"), ep(bid("io_mux"), "p_sel_periph")]),
        (ep(bid("region_decode"), "p_sel_gpu"), [ep(bid("bus_ctl"), "p_sel_gpu"), ep(bid("io_mux"), "p_sel_gpu")]),
        (ep(bid("bus_ctl"), "p_periph_we"), [top("periph_we")]),
        (ep(bid("bus_ctl"), "p_periph_re"), [top("periph_re")]),
        (top("periph_rdata"), [ep(bid("io_mux"), "p_periph_rdata")]),
        (ep(bid("region_decode"), "p_sel_ram"), [ep(bid("bus_ctl"), "p_sel_ram")]),
        (ep(bid("clint_decode4"), "p_kind"), [ep(bid("clint4"), "p_kind")]),
        (ep(bid("clint_decode4"), "p_hart"), [ep(bid("clint4"), "p_hart")]),
        (ep(bid("bus_ctl"), "p_clint_we"), [ep(bid("clint4"), "p_we")]),
        (ep(bid("clint4"), "p_rdata"), [ep(bid("io_mux"), "p_clint_rdata")]),
        (ep(bid("bus_ctl"), "p_uart_we"), [ep(bid("uart16550"), "p_we")]),
        (ep(bid("bus_ctl"), "p_uart_re"), [ep(bid("uart16550"), "p_re")]),
        (ep(bid("uart16550"), "p_rdata"), [ep(bid("io_mux"), "p_uart_rdata")]),
        (ep(bid("uart16550"), "p_irq"), [top("uart_irq"), ep(bid("plic4"), "p_s1")]),
        (ep(bid("uart16550"), "p_tx_valid"), [top("uart_tx_valid")]),
        (ep(bid("uart16550"), "p_tx_data"), [top("uart_tx_data")]),
        (ep(bid("bus_ctl"), "p_plic_we"), [ep(bid("plic4"), "p_we")]),
        (ep(bid("bus_ctl"), "p_plic_re"), [ep(bid("plic4"), "p_re")]),
        (ep(bid("io_mux"), "p_y"), [ep(bid("io_mux"), "p_y") if False else None]),
    ]
    if not PLIC:  # no controller: nothing drives or loads it
        pid = bid("plic4")
        links = [(d, [x for x in sk if x is None or x["blockId"] != pid]) for d, sk in links if d is not None and d["blockId"] != pid]
    links = [(d, [x for x in sk if x]) for d, sk in links if d is not None]
    links = [(d, sk) for d, sk in links if sk]
    # the one-driver rule: every driver port (and every top-level input) drives exactly one net; the sinks merge
    merged = {}
    order = []
    for drv, sinks in links:
        key = (drv["blockId"], drv["portId"])
        if key not in merged:
            merged[key] = {"driver": drv, "sinks": []}
            order.append(key)
        merged[key]["sinks"] += [x for x in sinks if x not in merged[key]["sinks"]]
    for n, key in enumerate(order):
        m = merged[key]
        nets.append({"id": f"n_q{n + 1:04d}", "name": f"q{n + 1:04d}", "width": 1, "driver": m["driver"], "sinks": m["sinks"],
                     "kind": "wire", "pipelineStage": 0})
    # the clock and reset of every block that has them and is not yet fed (the walkers, TLBs, reservations and gates run on the free clock)
    fed = {(e["blockId"], e["portId"]) for _, sk in links for e in sk if e["blockId"]}
    for b in blocks_all:
        for pt in b["ports"]:
            if pt["name"] in ("clk", "rst") and pt["direction"] in ("in", "input") and (b["id"], pt["id"]) not in fed:
                links.append((top(pt["name"]), [ep(b["id"], pt["id"])]))
    # merge again: one net per driver
    merged, order = {}, []
    for drv, sinks in links:
        key = (drv["blockId"], drv["portId"])
        if key not in merged:
            merged[key] = {"driver": drv, "sinks": []}
            order.append(key)
        merged[key]["sinks"] += [x for x in sinks if x not in merged[key]["sinks"]]
    width_of = {(b["id"], pt["id"]): pt["width"] for b in blocks_all for pt in b["ports"]}
    width_of.update({(None, f"t_{n}"): w for n, _, w, _ in TOPS})
    nets = []
    for n, key in enumerate(order):
        m = merged[key]
        w = width_of[(m["driver"]["blockId"], m["driver"]["portId"])]
        nets.append({"id": f"n_q{n + 1:04d}", "name": f"q{n + 1:04d}", "width": w, "driver": m["driver"], "sinks": m["sinks"],
                     "kind": "bus" if w > 1 else "wire", "pipelineStage": 0})
    return {"nets": nets, "blocks": blocks_all, "copies": copies, "origids": origids}


def write_design():
    d = design()
    tops = [{"id": f"t_{n}", "name": n, "direction": dr, "width": w, "role": r, "blockId": None} for n, dr, w, r in TOPS
            if (PLIC is False or n != "plic_rdata") and (GPU if n.startswith("gpu_") and n != "gpu_rdata" else True) and (not GPU if n == "gpu_rdata" else True)]
    out = {"id": "quad4", "name": "Quad-core SoC tile: four S-mode cores, Sv32 MMU per core, 16 MB shared RAM, CLINT for four harts, UART",
           "version": 1, "createdAt": "2026-11-20T00:00:00.000Z", "blocks": d["blocks"], "nets": d["nets"], "topLevelPorts": tops,
           "constraintGroups": [], "constraints": []}
    sfx = ("" if PLIC else "-noplic") + ("" if GPU else "-nogpu") + ("-fp" if FP else "") + ("-bp" if BP else "")
    (HERE / f"design-quad4{sfx}.json").write_text(json.dumps(out, indent=1))
    (HERE / f"copies4{sfx}.json").write_text(json.dumps(d["copies"], indent=1))
    # each block's original id (the stage-4 Verilog is keyed by it)
    origid = dict(d["origids"])
    (HERE / f"origid4{sfx}.json").write_text(json.dumps(origid, indent=1))
    return out


if __name__ == "__main__":
    d = write_design()
    print(len(d["blocks"]), "blocks", len(d["nets"]), "nets", len(d["topLevelPorts"]), "top-level ports")
