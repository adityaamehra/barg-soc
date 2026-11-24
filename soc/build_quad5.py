"""The quad-core SoC with the memory system (`quad5`): the quad4 SoC with its on-chip RAM replaced by external memory behind AXI4, and
instruction caches.

    python3 demos/quad-soc/build_quad5.py [--no-gpu] [--no-plic]    # writes design-quad5*.json, copies5*.json, origid5*.json

THE FINAL DESIGN IS THE DEFAULT: every hardware feature below is on unless left out with --no-<feature> (fp, bp, hier, periph, post, wfi, wa, tlb32, pmp, gpu);
the flags --fp, --bp, ... are still accepted and mean what they say.
Per hart k: the core (design-core-mem.json: quad4's core plus fetch_need_hi, fence_i, mem_is_amo), its TLBs and walker, rload, clock gate, an
instruction cache (curated set_assoc, 2 lookup ports, 4 KB), ifetch_ctl, hart_memif, and the glue for the cache's wide ports.
Shared: mem_arb (round robin over the harts' memory requests; devices complete at once, RAM goes through a transaction), the curated AXI4
master (axi_m), the curated memory model (ram_main, an AXI4 slave with 30 cycles of read latency), rsp_hold (the last response), selectors,
and the device side of quad4 unchanged. The data side is still uncached: every RAM load and store is a transaction.
The memory model keeps the name ram_main, so the testbenches load programs into dut.u_ram_main.u_ip.mem as before.
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
import ps2blocks as P2  # noqa: E402
import dispblocks as DSP  # noqa: E402
import devblocks as DV  # noqa: E402
import memblocks as MB
import fpblocks as FB  # (fp_or2 and fp_resmux are plain gates and a 2:1 mux: the data cache glue reuses them)  # noqa: E402
import subprocess  # noqa: E402
import importlib.util as _ilu  # noqa: E402
_sf = _ilu.spec_from_file_location("socfinal_blocks", HERE.parent / "soc-final" / "blocks.py")
SF = _ilu.module_from_spec(_sf)
_sf.loader.exec_module(SF)  # region_decode, bus_ctl, io_mux of the final memory map (64 MB RAM, 32 MB GPU window, peripheral window)
CLUSTER = json.loads((ROOT / "demos" / "gpu-cluster" / "design.json").read_text())

NC, W = 4, 32
GPU = "--no-gpu" not in sys.argv  # --no-gpu: the CPU-only build (the GPU window reads from the pin gpu_rdata); about 4x faster to simulate, for the Linux boot
PMP = "--no-pmp" not in sys.argv  # --pmp: sixteen PMP entries with enforcement in every core (fetch, data and page-walk accesses)
BP = "--no-bp" not in sys.argv  # --bp: cores with the gshare branch predictor
FP = "--no-fp" not in sys.argv  # --fp: cores with the F and D extensions (demos/linux-soc/design-core-mem-fp.json)
PERIPH = "--no-periph" not in sys.argv  # --periph: GPIO, SPI master and I2C master in the peripheral window (devblocks.py); their interrupts join PLIC sources 2 and 3
TLB32 = "--no-tlb32" not in sys.argv  # --tlb32: 32-entry TLBs (three per hart) instead of 8-entry ones
WA = "--no-wa" not in sys.argv  # --wa: the L3 allocates the line on a write miss (instead of writing around it to the DRAM)
WFI = "--no-wfi" not in sys.argv  # --wfi: a hart that executes WFI stops (its clock gate stays off) until an enabled interrupt is pending
POST = "--no-post" not in sys.argv  # --post: posted plain stores (postw): the core goes on when the engine has taken the store
HIER = "--no-hier" not in sys.argv  # --hier: the L2 (one per pair of harts) and the L3 between the memory engine and the AXI4 master
EXTMEM = "--ext-mem" in sys.argv  # FPGA: no memory model; the AXI4 master of the memory system is brought out as top-level ports m_axi_* (the board supplies the DDR behind them)
PS2 = "--no-ps2" not in sys.argv  # PS/2 keyboard and mouse ports (Altera UP register model) in the peripheral window, PLIC with sources 4 and 5 and a supervisor context per hart
PLIC = "--no-plic" not in sys.argv  # --no-plic: staging build without the interrupt controller (the cores take meip from the spare pin)
PS2 = PS2 and PERIPH and PLIC
PORTS = {"clk": None}


TOPS = [("clk", "in", 1, "clock"), ("rst", "in", 1, "reset"), ("rx_valid", "in", 1, "control"), ("rx_data", "in", 8, "data"),
        ("plic_rdata", "in", 32, "data"), ("ext_s2", "in", 1, "control"), ("ext_s3", "in", 1, "control"), ("meip", "in", 1, "control"),
        ("uart_irq", "out", 1, "control"), ("uart_tx_valid", "out", 1, "control"), ("uart_tx_data", "out", 8, "data"),
        ("periph_rdata", "in", 32, "data"), ("periph_we", "out", 1, "control"), ("periph_re", "out", 1, "control"),
        ("gpio_in", "in", 16, "data"), ("gpio_out", "out", 16, "data"), ("gpio_oe", "out", 16, "data"),
        ("spi_miso", "in", 1, "control"), ("spi_sclk", "out", 1, "control"), ("spi_mosi", "out", 1, "control"), ("spi_cs_n", "out", 4, "control"),
        ("i2c_scl_i", "in", 1, "control"), ("i2c_sda_i", "in", 1, "control"), ("i2c_scl_o", "out", 1, "control"), ("i2c_sda_o", "out", 1, "control"),
        *[(f"{pf}_{sg}", dr, 1, "control") for pf in ("ps2k", "ps2m") for sg, dr in (("clk_i", "in"), ("dat_i", "in"), ("clk_low", "out"), ("dat_low", "out"))],
        ("bus_addr", "out", 32, "addr"), ("bus_wdata", "out", 32, "data"),
        ("gpu_running", "out", 1, "control"), ("gpu_done", "out", 1, "control"), ("gpu_error", "out", 1, "control"),
        ("gpu_diverged", "out", 1, "control"), ("gpu_hsync", "out", 1, "control"), ("gpu_vsync", "out", 1, "control"),
        ("gpu_de", "out", 1, "control"), ("gpu_rgb", "out", 16, "data"), ("gpu_rdata", "in", 32, "data")]
_AXI = {"ar": ((("valid", 1), ("addr", 32), ("len", 8), ("size", 3), ("burst", 2)), (("ready", 1),)), "r": ((("ready", 1),), (("valid", 1), ("data", 32), ("resp", 2), ("last", 1))),
        "aw": ((("valid", 1), ("addr", 32), ("len", 8), ("size", 3), ("burst", 2)), (("ready", 1),)), "w": ((("valid", 1), ("data", 32), ("strb", 4), ("last", 1)), (("ready", 1),)),
        "b": ((("ready", 1),), (("valid", 1), ("resp", 2)))}
for _ch, (_o, _i) in _AXI.items():     # the AXI4 master port, in the order of the curated master (used with --ext-mem)
    TOPS += [(f"m_axi_{_ch}{n}", "out", w, "data") for n, w in _o] + [(f"m_axi_{_ch}{n}", "in", w, "data") for n, w in _i]


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


def curated(kind, params, name, desc, reset="sync"):
    """A curated IP block; its ports come from the catalogue itself."""
    js = subprocess.run(["node", "-e", "const ir=require('%s/packages/ir/dist/index.js');process.stdout.write(JSON.stringify(ir.ipPorts({kind:'%s',params:%s})));"
                         % (ROOT, kind, json.dumps(params))], capture_output=True, text=True, check=True).stdout
    return {"id": f"b_{name}", "name": name, "tier": "T3", "provenance": "curated", "moduleName": name, "description": desc,
            "ports": [{"id": f"p_{p['name']}", **p} for p in json.loads(js)], "clockDomain": "main", "resetStyle": reset, "latencyCycles": 0,
            "verified": True, "ip": {"kind": kind, "params": params}}


DRAM_PARAMS = {"DEPTH_W": 24, "READ_LAT": 30, "WRITE_LAT": 4, "JITTER": 0, "ERR_EN": 0, "ERR_IDX": 0}
ICACHE_PARAMS = {"SET_W": 9, "WAYS": 2, "LINE_W": 3, "READ_PORTS": 2, "STATE_W": 0, "DIRTY": 0}
L2_PARAMS = {"SET_W": 7, "WAYS": 8, "LINE_W": 3, "READ_PORTS": 8, "STATE_W": 0, "DIRTY": 0}     # 32 KB, write-through, never stale (every write invalidates)
L3_PARAMS = {"SET_W": 8, "WAYS": 16, "LINE_W": 3, "READ_PORTS": 8, "STATE_W": 0, "DIRTY": 1}    # 128 KB, write-back
DCACHE_PARAMS = {"SET_W": 8, "WAYS": 2, "LINE_W": 3, "READ_PORTS": 1, "STATE_W": 0, "DIRTY": 0}   # 4 KB, write-through, snoop-invalidated
_fc = [a for a in sys.argv if a == "--fpga-caches" or a.startswith("--fpga-caches=")]
FC_PARTS = set((_fc[0].split("=", 1)[1] if "=" in _fc[0] else "l1,l2,l3").split(",")) if _fc else set()    # --fpga-caches[=l1,l2,l3]: which caches get the small geometry (all three by default)
FPGAC = bool(FC_PARTS)   # FPGA: the arrays read combinationally on 2 to 8 ports, so they become LUT memory; small geometries keep that affordable (same logic, only the sizes differ)
# l1 l2 l3: the small geometry; l1m l2m l3m: four times that (a middle size, for finding the smallest set that boots)
if "l1" in FC_PARTS or "l1m" in FC_PARTS:
    ICACHE_PARAMS = {**ICACHE_PARAMS, "SET_W": 6 if "l1m" in FC_PARTS else 5}     # 4 KB / 8 KB
    DCACHE_PARAMS = {**DCACHE_PARAMS, "SET_W": 6 if "l1m" in FC_PARTS else 5}     # 1 KB / 2 KB
if "l2" in FC_PARTS or "l2m" in FC_PARTS:
    L2_PARAMS = {**L2_PARAMS, "SET_W": 5 if "l2m" in FC_PARTS else 3, "WAYS": 2}  # 2 KB / 8 KB
if "l3" in FC_PARTS or "l3m" in FC_PARTS:
    L3_PARAMS = {**L3_PARAMS, "SET_W": 6 if "l3m" in FC_PARTS else 4, "WAYS": 2}  # 2 KB / 8 KB


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
    core = json.loads((ROOT / "demos" / "linux-soc" / ("design-core-mem" + ("-fp" if FP else "") + ("-bp" if BP else "") + ("-pmp" if PMP else "") + ("-sext" if PS2 else "") + ".json")).read_text())
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
        "mem_arb": copy_as(MB.MEM_ARB, "mem_arb", bid("mem_arb")),
        "rsp_hold": copy_as(MB.RSP_HOLD, "rsp_hold", bid("rsp_hold")),
        "sm_ptw": copy_as(MB.SEL_MUX4, "sm_ptw", bid("sm_ptw")),
        "sm_if": copy_as(MB.SEL_MUX4, "sm_if", bid("sm_if")),
        "bm_amo": copy_as(MB.BIT_MUX4, "bm_amo", bid("bm_amo")),
        "eng_src_mux": copy_as(MB.SRC_MUX3, "eng_src_mux", bid("eng_src_mux")),
        "zeros": copy_as(MB.ZEROS, "zeros", bid("zeros")),
        "dc_wp": copy_as(spec("en_and"), "dc_wp", bid("dc_wp")),      # w_plain = c_store AND NOT c_amo (en_and: run AND NOT stall)
        "axi_m": curated("axi_master", {"BEATS_W": 3}, "axi_m", "AXI4 master: word read, 32-byte line read, word write"),
        "bus_mux4": copy_as(BQ.BUS_MUX4, "bus_mux4", bid("bus_mux4")),
        "region_decode": copy_as(SF.REGION_DECODE, "region_decode", bid("region_decode")),
        "bus_ctl": {**copy_as(MB.BUS_CTL_I, "bus_ctl", bid("bus_ctl")), "moduleName": "bus_ctl_i"},
        "clint_decode4": copy_as(BQ.CLINT_DECODE4, "clint_decode4", bid("clint_decode4")),
        "clint4": {**copy_as(MB.CLINT4_DIV, "clint4", bid("clint4")), "moduleName": "clint4_div"},
        "uart16550": copy_as(PB.UART16550F, "uart16550", bid("uart16550")),   # the 16550 with a 16-byte receive FIFO (periphblocks.py)
        "io_mux": copy_as(SF.IO_MUX, "io_mux", bid("io_mux")),
        "hart_cfg": copy_as(BQ.HART_CFG, "hart_cfg", bid("hart_cfg")),
        **({"plic4": ({**copy_as(MB.PLIC8, "plic4", bid("plic4")), "moduleName": "plic8"} if PS2 else copy_as(BQ.PLIC4, "plic4", bid("plic4")))} if PLIC else {}),
        "wlane": copy_as(spec("wlane"), "wlane", bid("wlane")),
        **({} if EXTMEM else {"ram_main": curated("dram", DRAM_PARAMS, "ram_main", "External memory model: 64 MB, AXI4 slave, 30 cycles read latency")}),
    }
    if POST:
        shared["postw"] = copy_as(MB.POSTW, "postw", bid("postw"))
    if PERIPH:
        shared.update({"pdev_bus": ({**copy_as(DSP.PDEV_BUS3, "pdev_bus", bid("pdev_bus")), "moduleName": "pdev_bus3"} if PS2 else copy_as(DV.PDEV_BUS, "pdev_bus", bid("pdev_bus"))), "gpio_regs": copy_as(DV.GPIO_REGS, "gpio_regs", bid("gpio_regs")),
                       "spi_regs": copy_as(DV.SPI_REGS, "spi_regs", bid("spi_regs")), "i2c_regs": copy_as(DV.I2C_REGS, "i2c_regs", bid("i2c_regs")),
                       "spi_m": curated("spi_master", {"DATA_W": 8, "CLK_DIV": 4, "CPOL": 0, "CPHA": 0, "LSB_FIRST": 0, "CS_W": 4}, "spi_m",
                                        "SPI master: 8-bit words, mode 0, four chip selects"),
                       "i2c_m": curated("i2c_master", {"CLK_DIV": 4, "STRETCH": 0}, "i2c_m", "I2C master: one byte per command"),
                       "irq_or2": copy_as(FB.FP_OR2, "irq_or2", bid("irq_or2")), "irq_or3": copy_as(FB.FP_OR2, "irq_or3", bid("irq_or3")),
                       "irq_or3b": copy_as(FB.FP_OR2, "irq_or3b", bid("irq_or3b"))})
    if PS2:   # two PS/2 ports: receiver, transmitter, 8-byte receive queue and the register block of each
        for pf in ("ps2k", "ps2m"):
            for part, sp in (("rx", P2.PS2_RX), ("tx", P2.PS2_TX), ("fifo", P2.PS2_FIFO), ("ctl", P2.PS2_CTL)):
                shared[f"{pf}_{part}"] = {**copy_as(sp, f"{pf}_{part}", bid(f"{pf}_{part}")), "moduleName": f"{pf}_{part}"}
            shared[f"{pf}_rxrst"] = copy_as(FB.FP_OR2, f"{pf}_rxrst", bid(f"{pf}_rxrst"))   # the receiver is held in reset while the host transmits (it would count the device's clock pulses as a received frame)
    if HIER:
        shared.update({
            "l2_ctl": {**copy_as(MB.L2_CTL_FW, "l2_ctl", bid("l2_ctl")), "moduleName": "l2_ctl_fw"}, "l3_ctl": {**copy_as(MB.L3_CTL_FW if WA else MB.L3_CTL, "l3_ctl", bid("l3_ctl")), **({"moduleName": "l3_ctl_fw"} if WA else {})},
            "la8_2": copy_as(MB.LINE_ADDRS8, "la8_2", bid("la8_2")), "la8_3": copy_as(MB.LINE_ADDRS8, "la8_3", bid("la8_3")),
            "h0_a": copy_as(MB.LO_BIT8, "h0_a", bid("h0_a")), "h0_b": copy_as(MB.LO_BIT8, "h0_b", bid("h0_b")), "h0_3": copy_as(MB.LO_BIT8, "h0_3", bid("h0_3")),
            "pair_or": copy_as(FB.FP_OR2, "pair_or", bid("pair_or")),
            "l2_array_a": curated("set_assoc", L2_PARAMS, "l2_array_a", "L2 for harts 0 and 1: 32 KB, 8 ways, write-through"),
            "l2_array_b": curated("set_assoc", L2_PARAMS, "l2_array_b", "L2 for harts 2 and 3: 32 KB, 8 ways, write-through"),
            "l3_array": curated("set_assoc", L3_PARAMS, "l3_array", "L3: 128 KB, 16 ways, write-back"),
        })
    base_of = {"mem_arb": "mem_arb", "rsp_hold": "rsp_hold", "sm_ptw": "sel_mux4", "sm_if": "sel_mux4", "bm_amo": "bit_mux4", "eng_src_mux": "src_mux3",
               "zeros": "zeros", "dc_wp": "en_and", "axi_m": "axi_m", "bus_mux4": "bus_mux4", "region_decode": "region_decode", "bus_ctl": "bus_ctl_i",
               "clint_decode4": "clint_decode4", "clint4": "clint4_div", "uart16550": "uart16550", "io_mux": "io_mux",
               "hart_cfg": "hart_cfg", "plic4": "plic8" if PS2 else "plic4", "wlane": "wlane", "ram_main": "ram_main",
               "l2_ctl": "l2_ctl_fw", "l3_ctl": "l3_ctl_fw" if WA else "l3_ctl", "la8_2": "line_addrs8", "la8_3": "line_addrs8", "h0_a": "lo_bit8", "h0_b": "lo_bit8", "h0_3": "lo_bit8",
               "pair_or": "fp_or2", "pdev_bus": "pdev_bus3" if PS2 else "pdev_bus",
               **({f"{pf}_{pt}": f"ps2_{pt}" for pf in ("ps2k", "ps2m") for pt in ("rx", "tx", "fifo", "ctl")} if PS2 else {}),
               **({f"{pf}_rxrst": "fp_or2" for pf in ("ps2k", "ps2m")} if PS2 else {}), "gpio_regs": "gpio_regs", "spi_regs": "spi_regs", "i2c_regs": "i2c_regs", "spi_m": "spi_m", "i2c_m": "i2c_m",
               "postw": "postw", "irq_or2": "fp_or2", "irq_or3": "fp_or2", "irq_or3b": "fp_or2", "l2_array_a": "l2_array_a", "l2_array_b": "l2_array_b", "l3_array": "l3_array"}
    origid = {"region_decode": "b_final_region_decode", "bus_ctl": "b_final_bus_ctl", "uart16550": "b_uart", "io_mux": "b_final_io_mux"}
    for n, b in shared.items():
        add_block(b, base_of[n], origid.get(n))

    # ------------------------------------------------------------------ the per-hart blocks
    TLB_SPEC = (lambda: copy.deepcopy(MB.TLB32)) if TLB32 else (lambda: spec("tlb"))   # noqa: E731
    TLB_BASE = "tlb32" if TLB32 else "tlb"
    per = {  # name -> (spec, base for the RTL, original id for stage-4 RTL or None)
        "tlb_ilo": (TLB_SPEC(), TLB_BASE), "tlb_ihi": (TLB_SPEC(), TLB_BASE), "tlb_d": (TLB_SPEC(), TLB_BASE),
        "ptw": (spec("ptw"), "ptw"),
        "hart_memif": (MB.HART_MEMIF, "hart_memif"), "ifetch_ctl": (MB.IFETCH_CTL, "ifetch_ctl"),
        "cat_lk": (MB.CAT64, "cat64"), "sp_lk": (MB.SPLIT64, "split64"), "sp_hit": (MB.SPLIT2, "split2"),
        "rload": (spec("rload"), "rload"),
        "en_and": (spec("en_and"), "en_and"), "en_and_clr": (spec("en_and"), "en_and"), "en_and_sf": (spec("en_and"), "en_and"),
        "core_gate": (copy.deepcopy(BQ.CORE_GATE), "core_gate"),
        "rsv_gate": (copy.deepcopy(BQ.RSV_GATE), "rsv_gate"),
        "amo_rsv": (stage4("amo_rsv"), "amo_rsv"),
        # the data cache: controller, the RAM-region decode of the hart's own address, and the glue (gates and muxes of accepted block types)
        "dcache_ctl": (MB.DCACHE_CTL, "dcache_ctl"), "dc_rd": (SF.REGION_DECODE, "region_decode"),
        **({"wfi_wake": (MB.WFI_WAKE2, "wfi_wake2"), "wfi_or": (FB.FP_OR2, "fp_or2")} if WFI else {}),
        "dc_hold": (FB.FP_OR2, "fp_or2"), "dc_or_ld": (FB.FP_OR2, "fp_or2"), "dc_or_ifq": (FB.FP_OR2, "fp_or2"), "dc_or_st": (FB.FP_OR2, "fp_or2"),
        "dc_en_rq": (spec("en_and"), "en_and"), "dc_dsel": (FB.FP_RESMUX, "fp_resmux"), "dc_aq": (MB.SEL_MUX4, "sel_mux4"),
    }
    ORIG = {"amo_rsv": "b_amo_rsv", "dc_rd": "b_final_region_decode"}
    for k in range(NC):
        for n, (sp, base) in per.items():
            add_block(copy_as(sp, f"c{k}_{n}", bid(n, k)), base, ORIG.get(n), k)
        add_block(curated("set_assoc", ICACHE_PARAMS, f"c{k}_icache", "Instruction cache: 32 KB, 2 ways, 32-byte lines, two lookup ports"), f"c{k}_icache", None, k)
        add_block(curated("set_assoc", DCACHE_PARAMS, f"c{k}_dcache", "Data cache: 4 KB, 2 ways, 32-byte lines, write-through, one lookup port"), f"c{k}_dcache", None, k)
        # the hart's core: the core design's blocks, renamed with the hart's prefix
        for cb in core["blocks"]:
            c = copy.deepcopy(cb)
            c["id"] = f"b_c{k}_" + cb["id"][2:]
            c["name"] = f"c{k}_{cb['name']}"
            c["moduleName"] = f"c{k}_{cb['moduleName']}"
            stem = re.sub(r"_(ilo|ihi|d|ptw)$", "", cb["name"])
            base = stem if stem in ("pa_mux", "perm_check", "xfault", "pmp_check") else ("fp_or2" if re.sub(r"_pmp_(ilo|ihi|d)$", "", cb["name"]) == "fp_or2" else ("ifault_pmp" if PMP and cb["name"] == "ifault" else ("mip_merge_s" if PS2 and cb["name"] == "mip_merge" else cb["name"])))
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
        **({"ext_seip": lambda k: ep(bid("plic4"), f"p_seip{k}")} if PS2 else {}),
        "sel_ram": lambda k: ep(bid("dc_rd", k), "p_sel_ram"),    # the hart's own decode: a load answered by its data cache has no grant, so the shared decoder shows another hart's address
        "ram_we": lambda k: ep(bid("bus_ctl"), "p_ram_we"),
        "is_io": lambda k: ep(bid("dc_rd", k), "p_is_io"),
        "io_raw": lambda k: ep(bid("io_mux"), "p_y"),
        "rsv_valid": lambda k: ep(bid("amo_rsv", k), "p_rsv_valid"),
        "rsv_addr": lambda k: ep(bid("amo_rsv", k), "p_rsv_addr"),
        "mtime": lambda k: ep(bid("clint4"), "p_mtime"),
        "inst_lo": lambda k: ep(bid("sp_lk", k), "p_lo"),
        "inst_hi": lambda k: ep(bid("sp_lk", k), "p_hi"),
        "tlb_ilo_hit": lambda k: ep(bid("tlb_ilo", k), "p_hit"), "tlb_ilo_ppa": lambda k: ep(bid("tlb_ilo", k), "p_ppa"),
        "tlb_ilo_flags": lambda k: ep(bid("tlb_ilo", k), "p_flags"),
        "tlb_ihi_hit": lambda k: ep(bid("tlb_ihi", k), "p_hit"), "tlb_ihi_ppa": lambda k: ep(bid("tlb_ihi", k), "p_ppa"),
        "tlb_ihi_flags": lambda k: ep(bid("tlb_ihi", k), "p_flags"),
        "tlb_d_hit": lambda k: ep(bid("tlb_d", k), "p_hit"), "tlb_d_ppa": lambda k: ep(bid("tlb_d", k), "p_ppa"),
        "tlb_d_flags": lambda k: ep(bid("tlb_d", k), "p_flags"),
        "ptw_busy": lambda k: ep(bid("ptw", k), "p_busy"), "ptw_fault": lambda k: ep(bid("ptw", k), "p_fault"),
        "ptw_fault_access": lambda k: ep(bid("ptw", k), "p_fault_access"),
        "ptw_fault_vpn": lambda k: ep(bid("ptw", k), "p_fault_vpn"),
        **({"ptw_addr": lambda k: ep(bid("ptw", k), "p_addr"), "ptw_req": lambda k: ep(bid("ptw", k), "p_req")} if PMP else {}),
    }
    OUT = {  # core output -> the sinks (per hart)
        "mem_alu_y": lambda k: [ep(bid("rload", k), "p_addr"), ep(bid("amo_rsv", k), "p_addr"), ep(bid("bus_mux4"), f"p_addr{k}"), ep(f"b_c{k}_dcache", "p_lk_addr"),
                                ep(bid("dcache_ctl", k), "p_addr"), ep(bid("dc_rd", k), "p_addr")],
        "fetch_need_hi": lambda k: [ep(bid("ifetch_ctl", k), "p_need_hi")],
        "fence_i": lambda k: [ep(bid("ifetch_ctl", k), "p_fence")],
        "mem_is_amo": lambda k: [ep(bid("bm_amo"), f"p_d{k}"), ep(bid("dcache_ctl", k), "p_is_amo")],
        "mem_store_data": lambda k: [ep(bid("bus_mux4"), f"p_store_data{k}")],
        "mem_memtype": lambda k: [ep(bid("rload", k), "p_memtype"), ep(bid("bus_mux4"), f"p_memtype{k}")],
        "mem_memsrc": lambda k: [ep(bid("bus_mux4"), f"p_memsrc{k}")],
        "mem_valid": lambda k: [ep(bid("bus_mux4"), f"p_valid{k}")],
        "mem_xcpt": lambda k: [ep(bid("bus_mux4"), f"p_xcpt{k}")],
        "mem_write": lambda k: [ep(bid("bus_mux4"), f"p_memwrite{k}"), ep(bid("dcache_ctl", k), "p_is_store")],
        "mem_kill": lambda k: [ep(bid("bus_mux4"), f"p_kill{k}")],
        "dmem_we": lambda k: [ep(bid("bus_mux4"), f"p_dmem_we{k}")],
        "dmem_wdata": lambda k: [ep(bid("bus_mux4"), f"p_dmem_wdata{k}")],
        "req": lambda k: [ep(bid("dc_en_rq", k), "p_run"), ep(bid("dcache_ctl", k), "p_req")],   # the request reaches hart_memif through dc_en_rq (masked on a cache hit or miss)
        "rsv_set": lambda k: [ep(bid("rsv_gate", k), "p_set_rsv")],
        "rsv_clr": lambda k: [ep(bid("rsv_gate", k), "p_clr_rsv")],
        "satp_ppn": lambda k: [ep(bid("ptw", k), "p_satp_ppn")],
        "sfence": lambda k: [ep(bid("en_and_sf", k), "p_run")],   # the flush counts on a cycle the core advances (see below)
        "fetch_pa_lo": lambda k: [ep(bid("cat_lk", k), "p_a"), ep(bid("ifetch_ctl", k), "p_lo_addr")],
        "fetch_pa_hi": lambda k: [ep(bid("cat_lk", k), "p_b"), ep(bid("ifetch_ctl", k), "p_hi_addr")],
        "va_ilo": lambda k: [ep(bid("tlb_ilo", k), "p_va")], "va_ihi": lambda k: [ep(bid("tlb_ihi", k), "p_va")],
        "va_d": lambda k: [ep(bid("tlb_d", k), "p_va")],
        "walk_va": lambda k: [ep(bid("ptw", k), "p_vaddr")], "walk_start": lambda k: [ep(bid("ptw", k), "p_start")],
        "mmu_stall": lambda k: [ep(bid("hart_memif", k), "p_mmu_stall"), ep(bid("ifetch_ctl", k), "p_hold"), ep(bid("dc_hold", k), "p_a")],
        "wb_redirect": lambda k: [ep(bid("en_and_clr", k), "p_run")],
        **({"ptw_deny": lambda k: [ep(bid("ptw", k), "p_deny")]} if PMP else {}),
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
    # ------------------------------------------------------------------ clock, reset, the pins
    dev_cr = [bid(d) for d in ("gpio_regs", "spi_regs", "i2c_regs", "spi_m", "i2c_m")] if PERIPH else []
    links.append((top("rst"), [ep(bid("clint4"), "p_rst"), ep(bid("uart16550"), "p_rst")] + [ep(b, "p_rst") for b in dev_cr]))
    links.append((top("clk"), [ep(bid("clint4"), "p_clk"), ep(bid("uart16550"), "p_clk")] + [ep(b, "p_clk") for b in dev_cr]))
    links.append((top("meip"), [ep(bid("hart_cfg"), "p_meip")]))
    links.append((ep(bid("plic4"), "p_rdata") if PLIC else top("plic_rdata"), [ep(bid("io_mux"), "p_plic_rdata")]))
    if PERIPH:    # source 2: the GPIO or the pin ext_s2; source 3: the SPI master, the I2C master or the pin ext_s3
        links += [(top("ext_s2"), [ep(bid("irq_or2"), "p_a")]), (ep(bid("gpio_regs"), "p_irq"), [ep(bid("irq_or2"), "p_b")]),
                  (ep(bid("irq_or2"), "p_y"), [ep(bid("plic4"), "p_s2")]),
                  (ep(bid("spi_regs"), "p_irq"), [ep(bid("irq_or3"), "p_a")]), (ep(bid("i2c_regs"), "p_irq"), [ep(bid("irq_or3"), "p_b")]),
                  (ep(bid("irq_or3"), "p_y"), [ep(bid("irq_or3b"), "p_a")]), (top("ext_s3"), [ep(bid("irq_or3b"), "p_b")]),
                  (ep(bid("irq_or3b"), "p_y"), [ep(bid("plic4"), "p_s3")])]
    else:
        links.append((top("ext_s2"), [ep(bid("plic4"), "p_s2")]))
        links.append((top("ext_s3"), [ep(bid("plic4"), "p_s3")]))
    links.append((top("rx_valid"), [ep(bid("uart16550"), "p_rx_valid")]))
    links.append((top("rx_data"), [ep(bid("uart16550"), "p_rx_data")]))
    # ------------------------------------------------------------------ per hart: requests, caches, the walker's and fetch's memory path
    zero = lambda p: ep(bid("zeros"), p)  # noqa: E731
    # with posted stores the core's grants and the write-complete pulse come from postw (a plain store is granted when the engine starts it)
    GRANT = (lambda k: ep(bid("postw"), f"p_go{k}")) if POST else (lambda k: ep(bid("mem_arb"), f"p_grant{k}"))   # noqa: E731
    WDONE = ep(bid("postw"), "p_wdone_o") if POST else ep(bid("mem_arb"), "p_wdone")
    if POST:
        pw = bid("postw")
        links += [(ep(bid("mem_arb"), "p_eng_start"), [ep(pw, "p_start")]), (ep(bid("mem_arb"), "p_eng_we"), [ep(pw, "p_we")]),
                  (ep(bid("bm_amo"), "p_y"), [ep(pw, "p_amo")]), (ep(bid("mem_arb"), "p_wdone"), [ep(pw, "p_wdone")]),
                  (top("clk"), [ep(pw, "p_clk")]), (top("rst"), [ep(pw, "p_rst")])]
        for k in range(NC):
            links += [(ep(bid("mem_arb"), f"p_grant{k}"), [ep(pw, f"p_g{k}")]), (ep(bid("mem_arb"), f"p_bsel{k}"), [ep(pw, f"p_b{k}")])]
    for k in range(NC):
        mf, ifc, ic = bid("hart_memif", k), bid("ifetch_ctl", k), f"b_c{k}_icache"
        links.append((ep(mf, "p_req"), [ep(bid("mem_arb"), f"p_req{k}")]))
        links.append((ep(mf, "p_kind"), [ep(bid("mem_arb"), f"p_kind{k}")]))
        # hold of the core: hart_memif's (walk, fetch miss) or the data cache's miss
        links.append((ep(mf, "p_stall"), [ep(bid("dc_or_st", k), "p_a")]))
        links.append((ep(bid("dcache_ctl", k), "p_dmiss"), [ep(bid("dc_or_st", k), "p_b"), ep(bid("dc_or_ld", k), "p_b")]))
        if WFI:   # the stall of the core (walk, fetch miss, data miss) or a WFI waiting for an interrupt
            wk, wo = bid("wfi_wake", k), bid("wfi_or", k)
            links.append((ep(bid("dc_or_st", k), "p_y"), [ep(wo, "p_a")]))
            links.append((ep(wk, "p_hold"), [ep(wo, "p_b")]))
            links += [(top("clk"), [ep(wk, "p_clk")]), (top("rst"), [ep(wk, "p_rst")])]   # the ungated clock: the wait counter runs while the hart is held
            links.append((ep(wo, "p_y"), [ep(bid("en_and", k), "p_stall"), ep(bid("en_and_clr", k), "p_stall"), ep(bid("en_and_sf", k), "p_stall")]))
            links.append((ep(bid("ex_mem", k), "p_inst_out"), [ep(wk, "p_inst")]))
            links.append((ep(bid("clint4"), f"p_msip{k}"), [ep(wk, "p_msip")]))
            links.append((ep(bid("clint4"), f"p_mtip{k}"), [ep(wk, "p_mtip")]))
            links.append((ep(bid("plic4"), f"p_meip{k}") if PLIC else ep(bid("hart_cfg"), f"p_meip{k}"), [ep(wk, "p_meip")]))
            links.append((ep(bid("csr_mregs", k), "p_mip_sw"), [ep(wk, "p_mip_sw")]))
            links.append((ep(bid("csr_mregs", k), "p_mie"), [ep(wk, "p_mie")]))
        else:
            links.append((ep(bid("dc_or_st", k), "p_y"), [ep(bid("en_and", k), "p_stall"), ep(bid("en_and_clr", k), "p_stall"), ep(bid("en_and_sf", k), "p_stall")]))
        # the core's request reaches the bus only when the data cache neither serves the load nor must refill for it
        links.append((ep(bid("dcache_ctl", k), "p_serve"), [ep(bid("dc_or_ld", k), "p_a"), ep(bid("dc_dsel", k), "p_sel")]))
        links.append((ep(bid("dc_or_ld", k), "p_y"), [ep(bid("dc_en_rq", k), "p_stall")]))
        links.append((ep(bid("dc_en_rq", k), "p_en"), [ep(mf, "p_core_req")]))
        # the data cache controller's view of the world
        links.append((ep(bid("dc_rd", k), "p_sel_ram"), [ep(bid("dcache_ctl", k), "p_is_ram")]))
        links.append((ep(bid("dc_hold", k), "p_y"), [ep(bid("dcache_ctl", k), "p_hold")]))
        links.append((ep(f"b_c{k}_dcache", "p_lk_hit"), [ep(bid("dcache_ctl", k), "p_hit")]))
        links.append((GRANT(k), [ep(bid("dcache_ctl", k), "p_done")]))
        links.append((ep(bid("rsp_hold"), "p_data"), [ep(bid("dcache_ctl", k), "p_line")]))
        links.append((WDONE, [ep(bid("dcache_ctl", k), "p_wdone")]))
        links.append((ep(bid("bus_mux4"), "p_addr"), [ep(bid("dcache_ctl", k), "p_waddr")]))
        links.append((ep(bid("mem_arb"), f"p_bsel{k}"), [ep(bid("dcache_ctl", k), "p_self")]))
        links.append((ep(bid("dc_wp"), "p_en"), [ep(bid("dcache_ctl", k), "p_w_plain")]))
        # refills: a line read like the fetch's, address from whichever controller wants it
        links.append((ep(ifc, "p_rq"), [ep(bid("dc_or_ifq", k), "p_a"), ep(bid("dc_aq", k), "p_sel0")]))
        links.append((ep(bid("dcache_ctl", k), "p_rq"), [ep(bid("dc_or_ifq", k), "p_b"), ep(bid("dc_aq", k), "p_sel1")]))
        links.append((ep(bid("dc_or_ifq", k), "p_y"), [ep(mf, "p_ifq")]))
        links.append((ep(ifc, "p_rq_addr"), [ep(bid("dc_aq", k), "p_d0")]))
        links.append((ep(bid("dcache_ctl", k), "p_rq_addr"), [ep(bid("dc_aq", k), "p_d1")]))
        links.append((ep(bid("dc_aq", k), "p_y"), [ep(bid("sm_if"), f"p_d{k}")]))
        # the array: fill, write update, invalidate; the word a hit returns
        dcn = f"b_c{k}_dcache"
        links.append((ep(bid("dcache_ctl", k), "p_fill_en"), [ep(dcn, "p_fill_en")]))
        links.append((ep(bid("dcache_ctl", k), "p_fill_addr"), [ep(dcn, "p_fill_addr")]))
        links.append((ep(bid("dcache_ctl", k), "p_fill_data"), [ep(dcn, "p_fill_data")]))
        links.append((ep(bid("dcache_ctl", k), "p_wr_en"), [ep(dcn, "p_wr_en")]))
        links.append((ep(bid("dcache_ctl", k), "p_wr_addr"), [ep(dcn, "p_wr_addr")]))
        links.append((ep(bid("wlane"), "p_data"), [ep(dcn, "p_wr_data")]))
        links.append((ep(bid("wlane"), "p_be"), [ep(dcn, "p_wr_be")]))
        links.append((ep(bid("dcache_ctl", k), "p_inv_en"), [ep(dcn, "p_inv_en")]))
        links.append((ep(bid("dcache_ctl", k), "p_inv_addr"), [ep(dcn, "p_inv_addr")]))
        links.append((zero("p_z1"), [ep(dcn, "p_fill_state"), ep(dcn, "p_inv_all"), ep(dcn, "p_st_en"), ep(dcn, "p_st_state"), ep(dcn, "p_st_clean")]))
        links.append((zero("p_z32"), [ep(dcn, "p_st_addr"), ep(bid("dc_aq", k), "p_d2"), ep(bid("dc_aq", k), "p_d3")]))
        links.append((zero("p_z1"), [ep(bid("dc_aq", k), "p_sel2"), ep(bid("dc_aq", k), "p_sel3")]))
        links.append((ep(dcn, "p_lk_data"), [ep(bid("dc_dsel", k), "p_from_fp")]))
        links.append((ep(bid("rsp_hold"), "p_word"), [ep(bid("dc_dsel", k), "p_from_alu")]))
        links.append((ep(bid("dc_dsel", k), "p_y"), [ep(bid("rload", k), "p_word")]))
        links.append((ep(mf, "p_run"), [ep(bid("en_and", k), "p_run")]))
        links.append((GRANT(k), [ep(mf, "p_grant"), ep(bid("rsv_gate", k), "p_self_grant"), ep(bid("ptw", k), "p_grant"),
                                                         ep(ifc, "p_done")]))
        links.append((ep(bid("mem_arb"), f"p_sel{k}"), [ep(bid("sm_ptw"), f"p_sel{k}"), ep(bid("sm_if"), f"p_sel{k}")]))
        links.append((ep(bid("mem_arb"), f"p_bsel{k}"), [ep(bid("bus_mux4"), f"p_grant{k}"), ep(bid("bm_amo"), f"p_sel{k}")]))
        links.append((ep(bid("ptw", k), "p_req"), [ep(mf, "p_ptw_req")]))
        links.append((ep(bid("ptw", k), "p_addr"), [ep(bid("sm_ptw"), f"p_d{k}")]))
        links.append((ep(ifc, "p_imiss"), [ep(mf, "p_imiss"), ep(bid("dc_hold", k), "p_b")]))
        links.append((ep(bid("en_and", k), "p_en"), [ep(bid("core_gate", k), "p_en"), ep(ifc, "p_adv")]))
        links.append((ep(bid("en_and_clr", k), "p_en"), [ep(bid("ptw", k), "p_clear")]))
        # sfence.vma flushes the TLBs only in a cycle the core advances: while the core waits for a page walk the instruction stays in write-back,
        # and a flush held every cycle would wipe each entry the walker fills (found by the FP Linux kernel, whose code patching hit it)
        links.append((ep(bid("en_and_sf", k), "p_en"), [ep(bid("tlb_ilo", k), "p_flush"), ep(bid("tlb_ihi", k), "p_flush"), ep(bid("tlb_d", k), "p_flush")]))
        # the instruction cache: two lookups (the fetch's two words), fills and the fence.i flush from ifetch_ctl, everything else tied off
        links.append((ep(bid("cat_lk", k), "p_y"), [ep(ic, "p_lk_addr")]))
        links.append((ep(ic, "p_lk_data"), [ep(bid("sp_lk", k), "p_y")]))
        links.append((ep(ic, "p_lk_hit"), [ep(bid("sp_hit", k), "p_y")]))
        links.append((ep(bid("sp_hit", k), "p_b0"), [ep(ifc, "p_hit_lo")]))
        links.append((ep(bid("sp_hit", k), "p_b1"), [ep(ifc, "p_hit_hi")]))
        links.append((ep(ifc, "p_fill_en"), [ep(ic, "p_fill_en")]))
        links.append((ep(ifc, "p_fill_addr"), [ep(ic, "p_fill_addr")]))
        links.append((ep(ifc, "p_fill_data"), [ep(ic, "p_fill_data")]))
        links.append((ep(ifc, "p_inv_all"), [ep(ic, "p_inv_all")]))
        links.append((ep(bid("rsp_hold"), "p_data"), [ep(ifc, "p_line")]))
        links.append((ep(bid("rsp_hold"), "p_word"), [ep(bid("ptw", k), "p_rdata")]))
        links.append((zero("p_z1"), [ep(ic, "p_wr_en"), ep(ic, "p_fill_state"), ep(ic, "p_inv_en"), ep(ic, "p_st_en"), ep(ic, "p_st_state"), ep(ic, "p_st_clean")]))
        links.append((zero("p_z4"), [ep(ic, "p_wr_be")]))
        links.append((zero("p_z32"), [ep(ic, "p_wr_addr"), ep(ic, "p_wr_data"), ep(ic, "p_inv_addr"), ep(ic, "p_st_addr")]))
        links.append((ep(bid("amo_rsv", k), "p_rsv_valid"), [ep(bid("rsv_gate", k), "p_rsv_valid")]))
        links.append((ep(bid("amo_rsv", k), "p_rsv_addr"), [ep(bid("rsv_gate", k), "p_rsv_addr")]))
        links.append((ep(bid("rsv_gate", k), "p_set"), [ep(bid("amo_rsv", k), "p_set")]))
        links.append((ep(bid("rsv_gate", k), "p_clear"), [ep(bid("amo_rsv", k), "p_clear")]))
        for t in ("tlb_ilo", "tlb_ihi", "tlb_d"):
            for sig in ("fill", "fill_vpn", "fill_ppn", "fill_mega", "fill_flags"):
                links.append((ep(bid("ptw", k), f"p_{sig}"), [ep(bid(t, k), f"p_{sig}")]))
    links.append((ep(bid("bus_mux4"), "p_memwrite"), [ep(bid("dc_wp"), "p_run")]))
    links.append((ep(bid("bm_amo"), "p_y"), [ep(bid("dc_wp"), "p_stall")]))
    # ------------------------------------------------------------------ the memory engine: arbiter, AXI4 master, the memory model
    arb, axi, mem = bid("mem_arb"), bid("axi_m"), bid("ram_main")
    links += [
        (ep(bid("region_decode"), "p_sel_ram"), [ep(arb, "p_is_ram"), ep(bid("bus_ctl"), "p_sel_ram")]),
        (ep(bid("bus_mux4"), "p_memwrite"), [ep(arb, "p_c_store"), ep(bid("bus_ctl"), "p_memwrite")]),
        (ep(bid("bus_mux4"), "p_dmem_we"), [ep(arb, "p_c_dmem_we")]),
        (ep(bid("bm_amo"), "p_y"), [ep(arb, "p_c_amo")]),
        (ep(arb, "p_eng_src"), [ep(bid("eng_src_mux"), "p_src")]),
        (ep(arb, "p_rdone"), [ep(bid("rsp_hold"), "p_done")]),
        (WDONE, [ep(bid("rsv_gate", k), "p_snoop_we") for k in range(NC)]),
        (ep(bid("sm_ptw"), "p_y"), [ep(bid("eng_src_mux"), "p_b")]),
        (ep(bid("sm_if"), "p_y"), [ep(bid("eng_src_mux"), "p_c")]),
    ]
    if not HIER:
        links += [
            (ep(arb, "p_eng_start"), [ep(axi, "p_req_valid")]), (ep(arb, "p_eng_we"), [ep(axi, "p_req_we")]), (ep(arb, "p_eng_line"), [ep(axi, "p_req_line")]),
            (ep(axi, "p_req_ready"), [ep(arb, "p_eng_ready"), ep(bid("bus_ctl"), "p_idle")]), (ep(axi, "p_resp_valid"), [ep(arb, "p_eng_done")]),
            (ep(axi, "p_resp_data"), [ep(bid("rsp_hold"), "p_line")]), (ep(bid("eng_src_mux"), "p_y"), [ep(axi, "p_req_addr")]),
            (ep(bid("wlane"), "p_data"), [ep(axi, "p_req_wdata")]), (ep(bid("wlane"), "p_be"), [ep(axi, "p_req_wstrb")]),
            (ep(bid("rsp_hold"), "p_data"), [ep(axi, "p_req_wline")]),    # no line writes without a hierarchy: any 256-bit net will do
        ]
    else:
        l2, l3 = bid("l2_ctl"), bid("l3_ctl")
        l2a, l2b, l3a = bid("l2_array_a"), bid("l2_array_b"), bid("l3_array")
        links += [
            # engine > L2 controller
            (ep(arb, "p_eng_start"), [ep(l2, "p_rv")]), (ep(arb, "p_eng_we"), [ep(l2, "p_rwe")]), (ep(arb, "p_eng_line"), [ep(l2, "p_rline")]),
            (ep(bid("eng_src_mux"), "p_y"), [ep(l2, "p_raddr")]), (ep(bid("wlane"), "p_data"), [ep(l2, "p_rwdata")]), (ep(bid("wlane"), "p_be"), [ep(l2, "p_rwstrb")]),
            (ep(arb, "p_sel2"), [ep(bid("pair_or"), "p_a")]), (ep(arb, "p_sel3"), [ep(bid("pair_or"), "p_b")]), (ep(bid("pair_or"), "p_y"), [ep(l2, "p_pair")]),
            (ep(l2, "p_ready"), [ep(arb, "p_eng_ready"), ep(bid("bus_ctl"), "p_idle")]), (ep(l2, "p_resp_valid"), [ep(arb, "p_eng_done")]), (ep(l2, "p_resp_data"), [ep(bid("rsp_hold"), "p_line")]),
            # L2 controller > L3 controller
            (ep(l2, "p_dv"), [ep(l3, "p_rv")]), (ep(l2, "p_dwe"), [ep(l3, "p_rwe")]), (ep(l2, "p_dline"), [ep(l3, "p_rline")]), (ep(l2, "p_daddr"), [ep(l3, "p_raddr")]),
            (ep(l2, "p_dwdata"), [ep(l3, "p_rwdata")]), (ep(l2, "p_dwstrb"), [ep(l3, "p_rwstrb")]),
            (ep(l3, "p_ready"), [ep(l2, "p_d_ready")]), (ep(l3, "p_resp_valid"), [ep(l2, "p_d_valid")]), (ep(l3, "p_resp_data"), [ep(l2, "p_d_data")]),
            # L3 controller > AXI4 master
            (ep(l3, "p_ax_valid"), [ep(axi, "p_req_valid")]), (ep(l3, "p_ax_we"), [ep(axi, "p_req_we")]), (ep(l3, "p_ax_line"), [ep(axi, "p_req_line")]),
            (ep(l3, "p_ax_addr"), [ep(axi, "p_req_addr")]), (ep(l3, "p_ax_wdata"), [ep(axi, "p_req_wdata")]), (ep(l3, "p_ax_wstrb"), [ep(axi, "p_req_wstrb")]),
            (ep(l3, "p_ax_wline"), [ep(axi, "p_req_wline")]), (ep(axi, "p_req_ready"), [ep(l3, "p_ax_ready")]), (ep(axi, "p_resp_valid"), [ep(l3, "p_ax_done")]),
            (ep(axi, "p_resp_data"), [ep(l3, "p_ax_data")]),
            # the two L2 arrays: the lookup address of the controller, both arrays, hit and line back; fill and invalidate from the controller
            (ep(l2, "p_lk_addr"), [ep(bid("la8_2"), "p_a")]), (ep(bid("la8_2"), "p_y"), [ep(l2a, "p_lk_addr"), ep(l2b, "p_lk_addr")]),
            (ep(l2a, "p_lk_hit"), [ep(bid("h0_a"), "p_y")]), (ep(l2b, "p_lk_hit"), [ep(bid("h0_b"), "p_y")]),
            (ep(bid("h0_a"), "p_b0"), [ep(l2, "p_hit_a")]), (ep(bid("h0_b"), "p_b0"), [ep(l2, "p_hit_b")]),
            (ep(l2a, "p_lk_data"), [ep(l2, "p_line_a")]), (ep(l2b, "p_lk_data"), [ep(l2, "p_line_b")]),
            (ep(l2, "p_fill_a_en"), [ep(l2a, "p_fill_en")]), (ep(l2, "p_fill_b_en"), [ep(l2b, "p_fill_en")]),
            (ep(l2, "p_fill_addr"), [ep(l2a, "p_fill_addr"), ep(l2b, "p_fill_addr")]), (ep(l2, "p_fill_data"), [ep(l2a, "p_fill_data"), ep(l2b, "p_fill_data")]),
            (ep(l2, "p_inv_en"), [ep(l2a, "p_inv_en"), ep(l2b, "p_inv_en")]), (ep(l2, "p_inv_addr"), [ep(l2a, "p_inv_addr"), ep(l2b, "p_inv_addr")]),
            (zero("p_z1"), [ep(a, p) for a in (l2a, l2b) for p in ("p_wr_en", "p_fill_state", "p_inv_all", "p_st_en", "p_st_state", "p_st_clean")]),
            (zero("p_z32"), [ep(a, p) for a in (l2a, l2b) for p in ("p_wr_addr", "p_wr_data", "p_st_addr")]),
            (zero("p_z4"), [ep(a, "p_wr_be") for a in (l2a, l2b)]),
            # the L3 array
            (ep(l3, "p_lk_addr"), [ep(bid("la8_3"), "p_a")]), (ep(bid("la8_3"), "p_y"), [ep(l3a, "p_lk_addr")]),
            (ep(l3a, "p_lk_hit"), [ep(bid("h0_3"), "p_y")]), (ep(bid("h0_3"), "p_b0"), [ep(l3, "p_hit")]), (ep(l3a, "p_lk_data"), [ep(l3, "p_lk_line")]),
            (ep(l3, "p_fill_en"), [ep(l3a, "p_fill_en")]), (ep(l3, "p_fill_addr"), [ep(l3a, "p_fill_addr")]), (ep(l3, "p_fill_data"), [ep(l3a, "p_fill_data")]),
            (ep(l3, "p_wr_en"), [ep(l3a, "p_wr_en")]), (ep(l3, "p_wr_addr"), [ep(l3a, "p_wr_addr")]), (ep(l3, "p_wr_data"), [ep(l3a, "p_wr_data")]),
            (ep(l3, "p_wr_be"), [ep(l3a, "p_wr_be")]),
            (ep(l3a, "p_vic_valid"), [ep(l3, "p_vic_valid")]), (ep(l3a, "p_vic_dirty"), [ep(l3, "p_vic_dirty")]),
            (ep(l3a, "p_vic_addr"), [ep(l3, "p_vic_addr")]), (ep(l3a, "p_vic_data"), [ep(l3, "p_vic_data")]),
            (zero("p_z1"), [ep(l3a, p) for p in ("p_fill_state", "p_inv_en", "p_inv_all", "p_st_en", "p_st_state", "p_st_clean")]),
            (zero("p_z32"), [ep(l3a, "p_inv_addr"), ep(l3a, "p_st_addr")]),
        ]
    for ch, ins, outs in (
        ("ar", ("valid", "addr", "len", "size", "burst"), ("ready",)), ("r", ("ready",), ("valid", "data", "resp", "last")),
        ("aw", ("valid", "addr", "len", "size", "burst"), ("ready",)), ("w", ("valid", "data", "strb", "last"), ("ready",)),
        ("b", ("ready",), ("valid", "resp")),
    ):
        for s in ins:
            links.append((ep(axi, f"p_m_axi_{ch}{s}"), [top(f"m_axi_{ch}{s}") if EXTMEM else ep(mem, f"p_s_axi_{ch}{s}")]))
        for s in outs:
            links.append((top(f"m_axi_{ch}{s}") if EXTMEM else ep(mem, f"p_s_axi_{ch}{s}"), [ep(axi, f"p_m_axi_{ch}{s}")]))
    # the granted bus (the RAM write path, the device side)
    for sig, sinks in (
        ("addr", [ep(bid("region_decode"), "p_addr"), ep(bid("clint_decode4"), "p_addr"), ep(bid("uart16550"), "p_addr"), ep(bid("plic4"), "p_addr"), top("bus_addr"),
                  ep(bid("eng_src_mux"), "p_a"), ep(bid("wlane"), "p_addr")] + [ep(bid("rsv_gate", k), "p_addr") for k in range(NC)]
                 + ([ep(bid(d), "p_pa" if d == "pdev_bus" else "p_addr") for d in ("pdev_bus", "gpio_regs", "spi_regs", "i2c_regs")] if PERIPH else [])
                 + ([ep(bid(f"{pf}_ctl"), "p_addr") for pf in ("ps2k", "ps2m")] if PS2 else [])),
        ("store_data", [ep(bid("clint4"), "p_wdata"), ep(bid("uart16550"), "p_wdata"), ep(bid("plic4"), "p_wdata"), top("bus_wdata")]
                       + ([ep(bid(d), "p_wdata") for d in ("gpio_regs", "spi_regs", "i2c_regs")] if PERIPH else [])
                       + ([ep(bid(f"{pf}_ctl"), "p_wdata") for pf in ("ps2k", "ps2m")] if PS2 else [])),
        ("memtype", [ep(bid("wlane"), "p_memtype")]),
        ("memsrc", [ep(bid("bus_ctl"), "p_memsrc")]),
        ("valid", [ep(bid("bus_ctl"), "p_valid")]),
        ("xcpt", [ep(bid("bus_ctl"), "p_xcpt")]),
        ("kill", [ep(bid("bus_ctl"), "p_kill")]),
        ("dmem_wdata", [ep(bid("wlane"), "p_wdata")]),
    ):
        links.append((ep(bid("bus_mux4"), f"p_{sig}"), sinks))
    links += [
        (ep(bid("region_decode"), "p_sel_clint"), [ep(bid("bus_ctl"), "p_sel_clint"), ep(bid("io_mux"), "p_sel_clint")]),
        (ep(bid("region_decode"), "p_sel_plic"), [ep(bid("bus_ctl"), "p_sel_plic"), ep(bid("io_mux"), "p_sel_plic")]),
        (ep(bid("region_decode"), "p_sel_uart"), [ep(bid("bus_ctl"), "p_sel_uart"), ep(bid("io_mux"), "p_sel_uart")]),
        (ep(bid("region_decode"), "p_sel_periph"), [ep(bid("bus_ctl"), "p_sel_periph"), ep(bid("io_mux"), "p_sel_periph")]),
        (ep(bid("region_decode"), "p_sel_gpu"), [ep(bid("bus_ctl"), "p_sel_gpu"), ep(bid("io_mux"), "p_sel_gpu")]),
        *([] if PERIPH else [(ep(bid("bus_ctl"), "p_periph_we"), [top("periph_we")])]),
        *([] if PERIPH else [(ep(bid("bus_ctl"), "p_periph_re"), [top("periph_re")])]),
        *([(ep(bid("pdev_bus"), "p_prdata"), [ep(bid("io_mux"), "p_periph_rdata")]),
           (ep(bid("bus_ctl"), "p_periph_we"), [ep(bid("pdev_bus"), "p_pw")]),
           (ep(bid("pdev_bus"), "p_gpio_we"), [ep(bid("gpio_regs"), "p_we")]), (ep(bid("pdev_bus"), "p_spi_we"), [ep(bid("spi_regs"), "p_we")]),
           (ep(bid("pdev_bus"), "p_i2c_we"), [ep(bid("i2c_regs"), "p_we")]),
           (ep(bid("gpio_regs"), "p_rdata"), [ep(bid("pdev_bus"), "p_gpio_rdata")]), (ep(bid("spi_regs"), "p_rdata"), [ep(bid("pdev_bus"), "p_spi_rdata")]),
           (ep(bid("i2c_regs"), "p_rdata"), [ep(bid("pdev_bus"), "p_i2c_rdata")]),
           (top("gpio_in"), [ep(bid("gpio_regs"), "p_pins")]), (ep(bid("gpio_regs"), "p_gpio_out"), [top("gpio_out")]),
           (ep(bid("gpio_regs"), "p_gpio_oe"), [top("gpio_oe")]),
           (ep(bid("spi_regs"), "p_tx_data"), [ep(bid("spi_m"), "p_tx_data")]), (ep(bid("spi_regs"), "p_tx_cs"), [ep(bid("spi_m"), "p_tx_cs")]),
           (ep(bid("spi_regs"), "p_tx_valid"), [ep(bid("spi_m"), "p_tx_valid")]), (ep(bid("spi_m"), "p_tx_ready"), [ep(bid("spi_regs"), "p_tx_ready")]),
           (ep(bid("spi_m"), "p_rx_data"), [ep(bid("spi_regs"), "p_rx_data")]), (ep(bid("spi_m"), "p_rx_valid"), [ep(bid("spi_regs"), "p_rx_valid")]),
           (ep(bid("spi_m"), "p_sclk"), [top("spi_sclk")]), (ep(bid("spi_m"), "p_mosi"), [top("spi_mosi")]), (top("spi_miso"), [ep(bid("spi_m"), "p_miso")]),
           (ep(bid("spi_m"), "p_cs_n"), [top("spi_cs_n")]),
           (ep(bid("i2c_regs"), "p_cmd_valid"), [ep(bid("i2c_m"), "p_cmd_valid")]), (ep(bid("i2c_m"), "p_cmd_ready"), [ep(bid("i2c_regs"), "p_cmd_ready")]),
           (ep(bid("i2c_regs"), "p_cmd_op"), [ep(bid("i2c_m"), "p_cmd_op")]), (ep(bid("i2c_regs"), "p_cmd_start"), [ep(bid("i2c_m"), "p_cmd_start")]),
           (ep(bid("i2c_regs"), "p_cmd_stop"), [ep(bid("i2c_m"), "p_cmd_stop")]), (ep(bid("i2c_regs"), "p_cmd_nack"), [ep(bid("i2c_m"), "p_cmd_nack")]),
           (ep(bid("i2c_regs"), "p_cmd_data"), [ep(bid("i2c_m"), "p_cmd_data")]),
           (ep(bid("i2c_m"), "p_rsp_valid"), [ep(bid("i2c_regs"), "p_rsp_valid")]), (ep(bid("i2c_m"), "p_rsp_data"), [ep(bid("i2c_regs"), "p_rsp_data")]),
           (ep(bid("i2c_m"), "p_rsp_nack"), [ep(bid("i2c_regs"), "p_rsp_nack")]), (ep(bid("i2c_m"), "p_rsp_arb_lost"), [ep(bid("i2c_regs"), "p_rsp_arb_lost")]),
           (ep(bid("i2c_m"), "p_scl_o"), [top("i2c_scl_o")]), (ep(bid("i2c_m"), "p_sda_o"), [top("i2c_sda_o")]),
           (top("i2c_scl_i"), [ep(bid("i2c_m"), "p_scl_i")]), (top("i2c_sda_i"), [ep(bid("i2c_m"), "p_sda_i")])] if PERIPH else
          [(top("periph_rdata"), [ep(bid("io_mux"), "p_periph_rdata")])]),
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
    if PS2:   # keyboard (device 3) and mouse (device 4): pins, receiver, transmitter, queue, registers, interrupts (PLIC sources 4 and 5)
        for pf, dev, src in (("ps2k", "kbd", 4), ("ps2m", "mouse", 5)):
            rx, tx, ff, cl = (bid(f"{pf}_{x}") for x in ("rx", "tx", "fifo", "ctl"))
            links += [(top(f"{pf}_clk_i"), [ep(rx, "p_clk_i"), ep(tx, "p_clk_i")]), (top(f"{pf}_dat_i"), [ep(rx, "p_dat_i"), ep(tx, "p_dat_i")]),
                      (ep(tx, "p_clk_low"), [top(f"{pf}_clk_low")]), (ep(tx, "p_dat_low"), [top(f"{pf}_dat_low")]),
                      (ep(rx, "p_valid"), [ep(ff, "p_push")]), (ep(rx, "p_dout"), [ep(ff, "p_din")]),
                      (ep(ff, "p_head"), [ep(cl, "p_head")]), (ep(ff, "p_count"), [ep(cl, "p_count")]), (ep(cl, "p_pop"), [ep(ff, "p_pop")]),
                      (ep(cl, "p_tx_start"), [ep(tx, "p_start")]), (ep(cl, "p_tx_data"), [ep(tx, "p_data")]),
                      (ep(tx, "p_busy"), [ep(cl, "p_tx_busy"), ep(bid(f"{pf}_rxrst"), "p_b")]), (top("rst"), [ep(bid(f"{pf}_rxrst"), "p_a")]),
                      (ep(bid(f"{pf}_rxrst"), "p_y"), [ep(rx, "p_rst")]), (ep(tx, "p_done"), [ep(cl, "p_tx_done")]), (ep(tx, "p_err"), [ep(cl, "p_tx_err")]),
                      (ep(bid("pdev_bus"), f"p_{dev}_we"), [ep(cl, "p_we")]), (ep(bid("pdev_bus"), f"p_{dev}_re"), [ep(cl, "p_re_pulse")]),
                      (ep(cl, "p_rdata"), [ep(bid("pdev_bus"), f"p_{dev}_rdata")]), (ep(cl, "p_irq"), [ep(bid("plic4"), f"p_s{src}")])]
        links.append((ep(bid("bus_ctl"), "p_periph_re"), [ep(bid("pdev_bus"), "p_pr")]))
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
            if (PLIC is False or n != "plic_rdata") and (n not in ("periph_rdata", "periph_we", "periph_re") if PERIPH else not n.startswith(("gpio_", "spi_", "i2c_"))) and (EXTMEM if n.startswith("m_axi_") else True) and (PS2 if n.startswith("ps2") else True) and (GPU if n.startswith("gpu_") and n != "gpu_rdata" else True) and (not GPU if n == "gpu_rdata" else True)]
    out = {"id": "quad5", "name": "Quad-core SoC with external memory: four S-mode cores, Sv32 MMU per core, instruction caches, AXI4 memory, CLINT, PLIC, UART",
           "version": 1, "createdAt": "2026-11-20T00:00:00.000Z", "blocks": d["blocks"], "nets": d["nets"], "topLevelPorts": tops,
           "constraintGroups": [], "constraints": []}
    sfx = ("" if PLIC else "-noplic") + ("" if GPU else "-nogpu") + ("-fp" if FP else "") + ("-bp" if BP else "") + ("-hier" if HIER else "") + ("-periph" if PERIPH else "") + ("-post" if POST else "") + ("-wfi" if WFI else "") + ("-wa" if WA else "") + ("-tlb32" if TLB32 else "") + ("-pmp" if PMP else "") + ("-ps2" if PS2 else "") + ("-extmem" if EXTMEM else "") + (("-fc" if FC_PARTS == {"l1", "l2", "l3"} else "-fc-" + "-".join(sorted(FC_PARTS))) if FPGAC else "")
    (HERE / f"design-quad5{sfx}.json").write_text(json.dumps(out, indent=1))
    (HERE / f"copies5{sfx}.json").write_text(json.dumps(d["copies"], indent=1))
    # each block's original id (the stage-4 Verilog is keyed by it)
    origid = dict(d["origids"])
    (HERE / f"origid5{sfx}.json").write_text(json.dumps(origid, indent=1))
    return out


if __name__ == "__main__":
    d = write_design()
    print(len(d["blocks"]), "blocks", len(d["nets"]), "nets", len(d["topLevelPorts"]), "top-level ports")
