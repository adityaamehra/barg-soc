"""The quad-core NuttX SoC.

    python3 demos/quad-soc/build_quad.py        # writes design-core.json (`rv-core-mc`) and design-quad.json (`quad-soc`)

* `rv-core-mc`: the stage-4 CPU core (54 blocks, the IP `rv_core`) plus three new blocks, for a core that shares its memory stage
  with other cores: `mem_req` (does the memory stage ask for the shared bus) and `hartid_patch` (mhartid reads the core's `hartid`
  input). The LR/SC reservation (`amo_rsv`) is not in the core: it must see other cores' stores while the core's clock is held, so
  it runs on the free clock outside, behind `rsv_gate` (the core's own set/clear only when it holds the bus; another core's store
  to the reserved word clears it). Its ports: the memory-stage
  signals out, the shared bus's answers in.
* `quad-soc`: four placed `rv_core` IPs, each behind a clock gate (`core_gate`: a core that asked for the bus and was not granted
  does not get the next clock edge, so the pipeline holds with no change inside), the arbiter `bus_arb` (round robin), the bus
  multiplexer `bus_mux4`, a four-hart CLINT (`clint4`, `clint_decode4`), `hart_cfg` (the hart ids; the PLIC reaches hart 0), and the
  stage-4 shared blocks: RAM banks, region decoder, bus strobes, device read mux, PLIC, UART.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "demos" / "gpu-soc"))
from build_gpu_soc import block, i, o, port  # noqa: E402
from make_core_ip import SHARED  # noqa: E402

STAGE4 = ROOT / "demos" / "nuttx-soc" / "design-a-16mb.json"
W, NC = 32, 4
OLD_SHARED = SHARED - {"clint", "clint_decode"}

CLK = port("p_clk", "clk", "in", 1, "clock")
RST = port("p_rst", "rst", "in", 1, "reset")

MEM_REQ = block("b_mem_req", "mem_req", """
    Combinational. Says whether the instruction in the memory stage asks for the shared bus. valid is 1 when the instruction is a
    real one, xcpt is 1 when it has raised an exception, kill is 1 when an older instruction is trapping in write-back, memsrc is the
    write-back source of the instruction (a load is 01), memwrite is 1 for a store that is really going to happen, is_amo is 1 for an
    atomic instruction. req is 1 when valid is 1, xcpt is 0, kill is 0 and (memsrc is 01 or memwrite is 1 or is_amo is 1), and 0
    otherwise. No clock, no reset, no state.
""", [i("valid", 1, "control"), i("xcpt", 1, "control"), i("kill", 1, "control"), i("memsrc", 2, "control"), i("memwrite", 1, "control"),
      i("is_amo", 1, "control"), o("req", 1, "control")])

RSV_GATE = block("b_rsv_gate", "rsv_gate", """
    Combinational. The set and clear of one core's load-reserved reservation, for a core that shares the bus with others. set_rsv and
    clr_rsv are the core's own strobes from its memory stage, self_grant is 1 when the core holds the bus this cycle (its access
    really happens). snoop_we is 1 when some core writes the RAM this cycle and addr (32 bits) is the address of that write.
    rsv_valid and rsv_addr (32 bits) are the core's held reservation. set is 1 when set_rsv is 1 and self_grant is 1, and 0
    otherwise. clear is 1 when clr_rsv is 1 and self_grant is 1, or when snoop_we is 1, self_grant is 0, rsv_valid is 1 and bits 31:2
    of addr equal bits 31:2 of rsv_addr; and 0 otherwise. No clock, no reset, no state.
""", [i("set_rsv", 1, "control"), i("clr_rsv", 1, "control"), i("self_grant", 1, "control"), i("snoop_we", 1, "control"),
      i("addr", W, "addr"), i("rsv_valid", 1, "control"), i("rsv_addr", W, "addr"), o("set", 1, "control"), o("clear", 1, "control")])

HARTID_PATCH = block("b_hartid_patch", "hartid_patch", """
    Combinational. The read value of a CSR, with the hart id filled in. csr_sel (5 bits) is the number of the register an instruction
    names, rdata (32 bits) the value the CSR file reads for it, hartid (2 bits) the number of this core. y is hartid (zero-extended
    to 32 bits) when csr_sel is 21 (MHARTID), and rdata for every other csr_sel. No clock, no reset, no state.
""", [i("csr_sel", 5, "control"), i("rdata", W), i("hartid", 2, "control"), o("y", W)])

CLINT_DECODE4 = block("b_clint_decode4", "clint_decode4", """
    Combinational. Names the register of a four-hart CLINT (the layout of QEMU's virt machine) that an address picks. Only bits 15:2 of
    addr (the word, w) are used. kind (3 bits) and hart (2 bits): kind 1 (msip) and hart w when w is 0 to 3 (offsets 0000 to 000C
    hexadecimal); kind 2 (mtimecmp, low word) and kind 3 (mtimecmp, high word) with hart (w - 1000 hexadecimal) / 2 when w is 1000
    to 1007 hexadecimal (offsets 4000 to 401C), low for an even w and high for an odd w; kind 4 (mtime, low word) and hart 0 when w
    is 2FFE hexadecimal (offset BFF8); kind 5 (mtime, high word) and hart 0 when w is 2FFF (offset BFFC); kind 0 and hart 0 for every
    other w. No clock, no reset, no state.
""", [i("addr", W, "addr"), o("kind", 3, "control"), o("hart", 2, "control")])

CLINT4 = block("b_clint4", "clint4", """
    Core-local interruptor for four harts. kind (3 bits) and hart (2 bits) name the register an access picks: kind 1 is msip of hart
    <hart> (bit 0 only; other bits read 0 and ignore writes), kinds 2 and 3 are the low and high words of mtimecmp of hart <hart> (64
    bits), kinds 4 and 5 are the low and high words of mtime (64 bits, one for all harts; hart is ignored), kinds 0, 6 and 7 name no
    register, which reads 0 and ignores writes. we is 1 for a store, with wdata the word stored. rdata is the register the access names
    before this cycle's write (0 when none); it depends only on kind, hart and the held state. At reset every msip is 0, mtime is 0 and
    every mtimecmp is all ones. On each rising clock edge, after reset: when we is 1 the register named is written (msip from wdata bit
    0, a half of a mtimecmp or of mtime from wdata); and mtime goes up by one (wrapping at 64 bits), except on an edge with a store to
    either half of mtime: that half becomes wdata, the other half keeps its value and mtime does not count. msip0 .. msip3 are the held
    msip bits. mtip<h> is 1 when the 64-bit unsigned mtime is greater than or equal to the 64-bit mtimecmp of hart h, as held (before
    this edge), and 0 otherwise. mtime (output, 64 bits) shows the held mtime.
""", [CLK, RST, i("kind", 3, "control"), i("hart", 2, "control"), i("wdata", W), i("we", 1, "control"), o("rdata", W), o("mtime", 64)] +
      [o(f"mtip{k}", 1, "control") for k in range(NC)] + [o(f"msip{k}", 1, "control") for k in range(NC)], reset="sync", latency=1)

BUS_ARB = block("b_bus_arb", "bus_arb", """
    Round-robin arbiter of the shared bus for four cores. req0 .. req3 say which cores ask for the bus. One register, last (2 bits): at
    reset it becomes 3; on each rising clock edge, after reset, when a grant is given it becomes the number of the core that got it,
    else it keeps its value. grant0 .. grant3 are combinational, from last and req0 .. req3: the cores are looked at in the order
    last + 1, last + 2, last + 3, last (each modulo 4) and the first one whose req is 1 gets its grant (grant<k> is 1 for that core k
    and 0 for the others); when no req is 1, every grant is 0. run<k> is 1 when req<k> is 0 or grant<k> is 1 (the core may go on),
    and 0 otherwise.
""", [CLK, RST] + [i(f"req{k}", 1, "control") for k in range(NC)] + [o(f"grant{k}", 1, "control") for k in range(NC)] +
      [o(f"run{k}", 1, "control") for k in range(NC)], reset="sync", latency=1)

SIGNALS = (("addr", W), ("store_data", W), ("memtype", 3), ("memsrc", 2), ("valid", 1), ("xcpt", 1), ("memwrite", 1), ("kill", 1),
           ("dmem_we", 1), ("dmem_wdata", W))
BUS_MUX4 = block("b_bus_mux4", "bus_mux4", """
    Combinational. The shared bus of four cores. grant0 .. grant3 are one bit each and at most one is 1. For each name in addr,
    store_data, memtype, memsrc, valid, xcpt, memwrite, kill, dmem_we and dmem_wdata the output is the input with that name and the
    number of the core whose grant is 1 (addr0 .. addr3 give addr, and so on); when no grant is 1, every output is 0. Widths: addr,
    store_data and dmem_wdata 32 bits, memtype 3, memsrc 2, the others 1. No clock, no reset, no state.
""", [i(f"grant{k}", 1, "control") for k in range(NC)] +
      [i(f"{n}{k}", w, "addr" if n == "addr" else "control" if w <= 3 else "data") for n, w in SIGNALS for k in range(NC)] +
      [o(n, w, "addr" if n == "addr" else "control" if w <= 3 else "data") for n, w in SIGNALS])

CORE_GATE = block("b_core_gate", "core_gate", """
    Clock gate of one core. clk is the clock, en says whether the core may take the next clock edge, rst is the reset. A latch holds
    the value of (en or rst): it follows that value while clk is 0 and keeps it while clk is 1. gclk is clk and the latch value
    (so gclk is 0 whenever clk is 0, and while en and rst are both 0 it stays 0 and the core gets no edge). The reset forces the clock on
    so that a core whose en is not yet known is still reset. No state besides the latch.
""", [port("p_clk", "clk", "in", 1, "clock"), i("en", 1, "control"), RST, port("p_gclk", "gclk", "out", 1, "clock")])

PLIC4 = block("b_plic4", "plic4", """
    Interrupt controller for four harts, with three level-triggered sources (s1, s2, s3; source numbers 1 to 3) and four contexts
    (context c is the machine external interrupt of hart c). Held state, all 0 at reset: prio of each source (3 bits), enable of each
    context (a 4-bit mask, bit s is source s; bit 0 is always 0), threshold of each context (3 bits), and in_service of each source
    (1 bit). eligible(c, s) is 1 when s_s is 1, in_service of s is 0, bit s of enable of c is 1, and prio of s is greater than the
    threshold of c. claim(c) is the number of the eligible source of context c with the highest prio (the lowest number on a tie), or 0
    when none is eligible. meip0 to meip3: meip<c> is 1 when claim(c) is not 0 (this cycle, from the held state and s1 to s3).
    The registers are named by off, the word offset: bits 25:2 of addr (32 bits; the layout of the SiFive PLIC; the other bits of addr are ignored): off 1, 2 and 3
    are prio of that source; off 400 hexadecimal is the pending word (bit s is s_s AND NOT in_service of s; bit 0 and bits 31:4 are 0);
    off 800 hexadecimal + 20 hexadecimal * c is enable of context c (bit s of the word, bits 3:1; the other bits read 0); off 80000
    hexadecimal + 400 hexadecimal * c is threshold of context c; off 80001 hexadecimal + 400 hexadecimal * c is the claim register of
    context c (c is 0 to 3). rdata (32 bits) is the register named by off as it is held now, zero-extended (the claim register gives
    claim(c)); it is 0 for every other off, and it does not depend on we or re. On each rising clock edge: rst is 1: every register
    becomes 0. Otherwise, when we is 1: a write to off 1 to 3 sets that prio to wdata bits 2:0; a write to the enable word of c sets
    enable of c to wdata bits 3:1 (bit 0 stays 0); a write to the threshold word of c sets threshold of c to wdata bits 2:0; a write to
    the claim register of c with wdata equal to 1, 2 or 3 clears in_service of that source; every other write changes nothing. When
    we is 0 and re is 1 and off is the claim register of c and claim(c) is not 0, in_service of claim(c) becomes 1 (the claim). At most
    one of we and re is 1.
""", [CLK, RST, i("we", 1, "control"), i("re", 1, "control"), i("addr", W, "addr"), i("wdata", W), i("s1", 1, "control"),
      i("s2", 1, "control"), i("s3", 1, "control"), o("rdata", W)] + [o(f"meip{k}", 1, "control") for k in range(NC)],
      reset="sync", latency=1)

WORD_ADDR24 = block("b_word_addr24", "word_addr24", """
    Combinational. The RAM word address of a byte address in a 64 MB RAM: addr (32 bits) bits 25:2 are word (24 bits). No clock, no
    reset, no state.
""", [i("addr", 32, "addr"), o("word", 24, "addr")])

PACK16W = block("b_pack16w", "pack16w", """
    Combinational. Sixteen 24-bit word addresses (a0 to a15) as one 384-bit bus: a0 in bits 23:0, a1 in bits 47:24, and so on, a15 in
    bits 383:360. bus384 is that bus. No clock, no reset, no state.
""", [i(f"a{k}", 24, "addr") for k in range(16)] + [o("bus384", 384, "addr")])

HART_CFG = block("b_hart_cfg", "hart_cfg", """
    Combinational. The configuration of four harts. meip is the PLIC's external interrupt (1 bit). meip0 is meip and meip1, meip2 and
    meip3 are 0 (the PLIC serves hart 0). hartid0 is 0, hartid1 is 1, hartid2 is 2 and hartid3 is 3 (2 bits each). No clock, no
    reset, no state.
""", [i("meip", 1, "control")] + [o(f"meip{k}", 1, "control") for k in range(NC)] + [o(f"hartid{k}", 2, "control") for k in range(NC)])


def end(b, p):
    return {"blockId": b, "portId": p}


def mk_net(nets, name, width, driver, sinks):
    nets.append({"id": f"n_{len(nets) + 1:03d}", "name": name, "width": width, "driver": driver, "sinks": list(sinks),
                 "kind": "bus" if width > 1 else "wire", "pipelineStage": 0})


def tops(ports):
    return [{**p, "blockId": None} for p in ports]


def core_design() -> dict:
    s4 = json.loads(STAGE4.read_text())
    core = {b["id"]: b for b in s4["blocks"] if b["name"] not in SHARED | {"amo_rsv"}}
    by_name = {b["name"]: b for b in s4["blocks"]}
    out_nets = {"mem_alu_y": "mem_alu_y", "mem_store_data": "mem_store_data", "mem_memtype": "mem_memtype", "mem_memsrc": "mem_memsrc",
                "mem_valid": "mem_valid", "mem_xcpt": "mem_xcpt", "mem_memwrite_ok": "mem_write", "wb_redirect": "mem_kill",
                "dmem_we": "dmem_we", "dmem_wdata": "dmem_wdata"}
    in_nets = ("memory_read", "ext_msip", "ext_mtip", "ext_meip", "sel_ram", "ram_we", "is_io", "io_raw")
    width = {n["name"]: n["width"] for n in s4["nets"]}
    role = {"mem_alu_y": "addr", "mem_memtype": "control", "mem_memsrc": "control"}
    ports_in = [port("t_clk", "clk", "in", 1, "clock"), port("t_rst", "rst", "in", 1, "reset"), port("t_hartid", "hartid", "in", 2, "control")]
    ports_in += [port(f"t_{n}", n, "in", width[n], "data" if width[n] > 3 else "control") for n in in_nets]
    ports_in += [port("t_rsv_valid", "rsv_valid", "in", 1, "control"), port("t_rsv_addr", "rsv_addr", "in", W, "addr")]
    ports_out = [port(f"t_{v}", v, "out", width[k], role.get(k, "data" if width[k] > 3 else "control")) for k, v in out_nets.items()]
    ports_out += [port("t_req", "req", "out", 1, "control"), port("t_rsv_set", "rsv_set", "out", 1, "control"),
                  port("t_rsv_clr", "rsv_clr", "out", 1, "control")]
    nets, blocks = [], list(core.values()) + [MEM_REQ, HARTID_PATCH]
    for n in s4["nets"]:
        drv, sinks = n["driver"], [s for s in n["sinks"] if s["blockId"] in core]
        name = n["name"]
        if drv["blockId"] is None:
            if name in ("clock", "reset"):
                mk_net(nets, name, 1, end(None, "t_clk" if name == "clock" else "t_rst"), sinks)
            continue
        if drv["blockId"] in core:
            if name in out_nets:
                sinks.append(end(None, f"t_{out_nets[name]}"))
            if name == "csr_rdata":        # through the hart id patch
                mk_net(nets, "csr_rdata", W, drv, [end("b_hartid_patch", "p_rdata")])
                mk_net(nets, "csr_rdata_hart", W, end("b_hartid_patch", "p_y"), sinks)
                continue
            if name in ("rsv_set", "rsv_clear"):          # to the reservation outside the core
                mk_net(nets, name, 1, drv, [end(None, "t_rsv_set" if name == "rsv_set" else "t_rsv_clr")])
                continue
            extra = {"mem_valid": [end("b_mem_req", "p_valid")], "mem_xcpt": [end("b_mem_req", "p_xcpt")],
                     "wb_redirect": [end("b_mem_req", "p_kill")], "mem_memsrc": [end("b_mem_req", "p_memsrc")],
                     "mem_memwrite_ok": [end("b_mem_req", "p_memwrite")]}.get(name, [])
            if sinks or extra:
                mk_net(nets, name, n["width"], drv, sinks + extra)
        elif sinks:                          # driven outside the core: a top-level input
            if name in ("rsv_valid", "rsv_addr"):
                continue
            assert name in in_nets, name
            mk_net(nets, name, n["width"], end(None, f"t_{name}"), sinks)
    csr_sel = next(n for n in s4["nets"] if any(s["blockId"] == "b_csr_file" and s["portId"] == "p_csr_sel" for s in n["sinks"]))
    next(n for n in nets if n["name"] == csr_sel["name"])["sinks"].append(end("b_hartid_patch", "p_csr_sel"))
    mk_net(nets, "hartid", 2, end(None, "t_hartid"), [end("b_hartid_patch", "p_hartid")])
    for src in ("rsv_valid", "rsv_addr"):
        mk_net(nets, src, 1 if src == "rsv_valid" else W, end(None, f"t_{src}"), [end("b_amo_match", f"p_{src}")])
    mk_net(nets, "mem_req", 1, end("b_mem_req", "p_req"), [end(None, "t_req")])
    mk_net(nets, "mem_is_amo_req", 1, end("b_ex_mem", "p_is_amo_out"), [end("b_mem_req", "p_is_amo")])
    return {**{k: v for k, v in s4.items() if k not in ("blocks", "nets", "topLevelPorts", "referenceMaterial")}, "id": "rv-core-mc",
            "name": "RV32IMAC core for a shared memory bus (stage-4 core + request, reservation snoop, hart id)",
            "blocks": blocks, "nets": nets, "topLevelPorts": tops(ports_in + ports_out)}


def quad_design(core_ref: dict, core: dict) -> dict:
    s4 = json.loads(STAGE4.read_text())
    cp = [{k: v for k, v in p.items() if k != "blockId"} for p in core["topLevelPorts"]]
    blocks = [b for b in s4["blocks"] if b["name"] in OLD_SHARED] + [CLINT_DECODE4, CLINT4, BUS_ARB, BUS_MUX4, HART_CFG]
    for k in range(NC):
        blocks.append({"id": f"b_core{k}", "name": f"u_core{k}", "tier": "T1", "moduleName": f"rv_core{k}", "clockDomain": "main",
                       "resetStyle": "none", "latencyCycles": 0, "verified": True, "ports": cp, "ipRef": core_ref,
                       "description": f"IP rv_core v{core_ref['version']}: core {k}, not generated again"})
        r = copy.deepcopy(next(b for b in s4["blocks"] if b["name"] == "amo_rsv"))
        r["id"], r["name"], r["moduleName"] = f"b_rsv{k}", f"amo_rsv{k}", f"amo_rsv{k}"
        rg = copy.deepcopy(RSV_GATE)
        rg["id"], rg["name"], rg["moduleName"] = f"b_rsvg{k}", f"rsv_gate{k}", f"rsv_gate{k}"
        blocks += [r, rg]
        g = copy.deepcopy(CORE_GATE)
        g["id"], g["name"], g["moduleName"] = f"b_gate{k}", f"core_gate{k}", f"core_gate{k}"
        blocks.append(g)
    shared = {b["id"]: b for b in blocks}
    ids = {b["name"]: b["id"] for b in s4["blocks"]}
    nets: list[dict] = []
    for n in s4["nets"]:
        drv, name = n["driver"], n["name"]
        sinks = [s for s in n["sinks"] if s["blockId"] is None or s["blockId"] in shared]
        if drv["blockId"] is None:
            if name in ("clock", "reset"):
                pin = "p_clk" if name == "clock" else "p_rst"
                sinks = [s for s in sinks if s["blockId"] not in (ids["clint"],)]
                sinks += [end(f"b_gate{k}", "p_clk" if name == "clock" else "p_rst") for k in range(NC)]
                sinks += [end(b, pin) for b in ("b_clint4", "b_bus_arb")] + [end(f"b_rsv{k}", pin) for k in range(NC)]
                if name == "reset":
                    sinks += [end(f"b_core{k}", "t_rst") for k in range(NC)]
                mk_net(nets, name, 1, drv, sinks)
            elif sinks:
                mk_net(nets, name, n["width"], drv, sinks)
            continue
        if drv["blockId"] not in shared and drv["blockId"] not in (ids["clint"], ids["clint_decode"]) and drv["blockId"] in {
                b["id"] for b in s4["blocks"]}:
            bus = {"mem_alu_y": "addr", "mem_store_data": "store_data", "mem_memtype": "memtype", "mem_memsrc": "memsrc",
                   "mem_valid": "valid", "mem_xcpt": "xcpt", "mem_memwrite_ok": "memwrite", "wb_redirect": "kill",
                   "dmem_we": "dmem_we", "dmem_wdata": "dmem_wdata"}
            if name in bus:
                sinks = [s for s in sinks if s["blockId"] != ids["clint"]] + ([end("b_clint4", "p_wdata")] if name == "mem_store_data" else [])
                sinks = [end("b_clint_decode4", "p_addr") if s["blockId"] == ids["clint_decode"] else s for s in sinks]
                if name == "mem_alu_y":
                    sinks.append(end("b_gate0", "p_gclk")) if False else None
                mk_net(nets, name, n["width"], end("b_bus_mux4", f"p_{bus[name]}"), sinks)
            continue
        if drv["blockId"] in (ids["clint"], ids["clint_decode"]):
            continue
        if name in ("sel_ram", "is_io", "ram_we", "io_raw", "memory_read"):
            sinks += [end(f"b_core{k}", f"t_{name}") for k in range(NC)]
        if name == "ext_meip":
            continue
        if sinks:
            mk_net(nets, name, n["width"], drv, sinks)
    # the CLINT, interrupts, hart ids
    mk_net(nets, "clint_kind", 3, end("b_clint_decode4", "p_kind"), [end("b_clint4", "p_kind")])
    mk_net(nets, "clint_hart", 2, end("b_clint_decode4", "p_hart"), [end("b_clint4", "p_hart")])
    mk_net(nets, "clint_we", 1, end(ids["bus_ctl"], "p_clint_we"), [end("b_clint4", "p_we")])
    mk_net(nets, "clint_rdata", W, end("b_clint4", "p_rdata"), [end(ids["io_mux"], "p_clint_rdata")])
    mk_net(nets, "meip_plic", 1, end(ids["plic_logic"], "p_meip"), [end("b_hart_cfg", "p_meip")])
    for k in range(NC):
        c = f"b_core{k}"
        mk_net(nets, f"ext_msip{k}", 1, end("b_clint4", f"p_msip{k}"), [end(c, "t_ext_msip")])
        mk_net(nets, f"ext_mtip{k}", 1, end("b_clint4", f"p_mtip{k}"), [end(c, "t_ext_mtip")])
        mk_net(nets, f"ext_meip{k}", 1, end("b_hart_cfg", f"p_meip{k}"), [end(c, "t_ext_meip")])
        mk_net(nets, f"hartid{k}", 2, end("b_hart_cfg", f"p_hartid{k}"), [end(c, "t_hartid")])
        # the core's clock is its gate's output; its memory-stage outputs go to the bus multiplexer
        mk_net(nets, f"gclk{k}", 1, end(f"b_gate{k}", "p_gclk"), [end(c, "t_clk")])
        mk_net(nets, f"req{k}", 1, end(c, "t_req"), [end("b_bus_arb", f"p_req{k}")])
        mk_net(nets, f"run{k}", 1, end("b_bus_arb", f"p_run{k}"), [end(f"b_gate{k}", "p_en")])
        mk_net(nets, f"grant{k}", 1, end("b_bus_arb", f"p_grant{k}"), [end("b_bus_mux4", f"p_grant{k}")])
        for src, dst in (("mem_alu_y", "addr"), ("mem_store_data", "store_data"), ("mem_memtype", "memtype"), ("mem_memsrc", "memsrc"),
                         ("mem_valid", "valid"), ("mem_xcpt", "xcpt"), ("mem_write", "memwrite"), ("mem_kill", "kill"),
                         ("dmem_we", "dmem_we"), ("dmem_wdata", "dmem_wdata")):
            w = next(p["width"] for p in cp if p["name"] == src)
            mk_net(nets, f"{src}{k}", w, end(c, f"t_{src}"), [end("b_bus_mux4", f"p_{dst}{k}")])
    # each core's reservation, on the free clock: its own set/clear when it holds the bus, other cores' RAM writes clear it
    by = {n["name"]: n for n in nets}
    for k in range(NC):
        c, g, r = f"b_core{k}", f"b_rsvg{k}", f"b_rsv{k}"
        by[f"grant{k}"]["sinks"].append(end(g, "p_self_grant"))
        by["mem_alu_y"]["sinks"].append(end(g, "p_addr"))
        by["dmem_we"]["sinks"].append(end(g, "p_snoop_we"))
        by[f"mem_alu_y{k}"]["sinks"].append(end(r, "p_addr"))
        mk_net(nets, f"rsv_set_req{k}", 1, end(c, "t_rsv_set"), [end(g, "p_set_rsv")])
        mk_net(nets, f"rsv_clr_req{k}", 1, end(c, "t_rsv_clr"), [end(g, "p_clr_rsv")])
        mk_net(nets, f"rsv_set{k}", 1, end(g, "p_set"), [end(r, "p_set")])
        mk_net(nets, f"rsv_clear{k}", 1, end(g, "p_clear"), [end(r, "p_clear")])
        mk_net(nets, f"rsv_valid{k}", 1, end(r, "p_rsv_valid"), [end(c, "t_rsv_valid"), end(g, "p_rsv_valid")])
        mk_net(nets, f"rsv_addr{k}", W, end(r, "p_rsv_addr"), [end(c, "t_rsv_addr"), end(g, "p_rsv_addr")])
    tops_ = [p for p in s4["topLevelPorts"] if p["name"] in ("clk", "rst", "mem_addr", "mem_wdata", "mem_write", "uart_rx_valid",
                                                             "uart_rx_data", "uart_tx_valid", "uart_tx_data")]
    return {**{k: v for k, v in s4.items() if k not in ("blocks", "nets", "topLevelPorts", "referenceMaterial")}, "id": "quad-soc",
            "name": "Quad-core NuttX SoC (four rv_core IPs, shared RAM, one CLINT/PLIC/UART)", "blocks": blocks, "nets": nets,
            "topLevelPorts": tops_}


def validate(d: dict) -> None:
    ports = {(b["id"], p["id"]): p for b in d["blocks"] for p in b["ports"]}
    tp = {p["id"]: p for p in d["topLevelPorts"]}
    driven = {}
    for n in d["nets"]:
        dr = n["driver"]
        assert (dr["blockId"] is None and dr["portId"] in tp) or (dr["blockId"], dr["portId"]) in ports, (n["name"], dr)
        for s in n["sinks"]:
            assert (s["blockId"] is None and s["portId"] in tp) or (s["blockId"], s["portId"]) in ports, (n["name"], s)
            if s["blockId"] is not None:
                assert (s["blockId"], s["portId"]) not in driven, ("driven twice", n["name"], s, driven[(s["blockId"], s["portId"])])
                driven[(s["blockId"], s["portId"])] = n["name"]
    miss = [k for k, p in ports.items() if p["direction"] == "in" and k not in driven]
    assert not miss, f"undriven inputs: {miss[:12]}"


if __name__ == "__main__":
    core = core_design()
    validate(core)
    (HERE / "design-core.json").write_text(json.dumps(core, indent=2) + "\n")
    print(f"design-core.json: {len(core['blocks'])} blocks, {len(core['nets'])} nets, {len(core['topLevelPorts'])} ports")
    ref_path = HERE / "core-ref.json"
    if ref_path.exists():
        quad = quad_design(json.loads(ref_path.read_text()), core)
        validate(quad)
        (HERE / "design-quad.json").write_text(json.dumps(quad, indent=2) + "\n")
        print(f"design-quad.json: {len(quad['blocks'])} blocks, {len(quad['nets'])} nets")
