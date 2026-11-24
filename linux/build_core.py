"""The core with supervisor mode and an MMU (`rv-core-s`), built from the shared-bus core (`demos/quad-soc/design-core.json`).

    python3 demos/linux-soc/build_core.py        # writes demos/linux-soc/design-core.json

Removed: csr_file, csr_addr_decode, irq_pending, hartid_patch (the machine-only CSRs), imem and imem_hi (instruction memory moves
out of the core: it is written by the bus on the free clock). Replaced in place (same ids, more ports): sys_decode (sret,
sfence.vma, fence.i, fetch-fault words, ecall by privilege), ex_xcpt (data page faults, fetch-fault trap values).
Added (demos/linux-soc/blocks.py): the CSR group, and the combinational half of the MMU: xlate_on, satp_split, dkind, three
pa_mux, three perm_check, three xfault (fetch word, next fetch word, data), ifault, mmu_ctl.
Outside the core (the core tile, on the free clock): the three TLBs, the walker, the instruction memory, the reservation.

New core ports: in: mtime (64), inst_lo, inst_hi (the instruction memory's two words), the three TLB answers (hit, ppa, flags),
the walker's state (busy, fault, fault_access, fault_vpn). out: fetch_pa_lo, fetch_pa_hi, vpn_ilo, vpn_ihi, vpn_d, sfence,
satp_ppn, mmu_stall, walk_start, walk_va.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import blocks as B  # noqa: E402
sys.path.insert(0, str(HERE.parent / "quad-soc"))
import memblocks as MB  # noqa: E402  (the memory-system variant's extra blocks)
import fpblocks as FB  # noqa: E402  (the floating-point side)
import bpblocks as BPB  # noqa: E402  (the branch predictor)
import subprocess  # noqa: E402

W = 32
REMOVE = {"csr_file", "csr_addr_decode", "irq_pending", "hartid_patch", "imem", "imem_hi"}  # instruction fetch: the shared RAM (next block)


def inst(blk: dict, suffix: str) -> dict:
    b = copy.deepcopy(blk)
    b["id"], b["name"], b["moduleName"] = f"{blk['id']}_{suffix}", f"{blk['name']}_{suffix}", f"{blk['name']}_{suffix}"
    return b


def fpu_block() -> dict:
    """The curated floating-point unit (catalogue kind fpu); its ports come from the catalogue."""
    js = subprocess.run(["node", "-e", "const ir=require('%s/packages/ir/dist/index.js');process.stdout.write(JSON.stringify(ir.ipPorts({kind:'fpu',params:{}})));" % ROOT],
                        capture_output=True, text=True, check=True).stdout
    return {"id": "b_fpu", "name": "fpu", "tier": "T3", "provenance": "curated", "moduleName": "fpu", "description": "RV32 F and D floating-point unit (curated barg_fpu)",
            "ports": [{"id": f"p_{q['name']}", **q} for q in json.loads(js)], "clockDomain": "main", "resetStyle": "sync", "latencyCycles": 0,
            "verified": True, "ip": {"kind": "fpu", "params": {}}}


def wire_fp(nets, net, ids, e, add, sink, clk, rst) -> None:
    """Joins the floating-point side (demos/quad-soc/fpblocks.py and the curated FPU) to the core; the core's own blocks stay as they are.
    Decode: fp_dec turns an FP instruction into a harmless integer one for the integer decoders (its original word still travels in the pipeline);
    execute: fp_exdec, the FPU with fp_seq, fregfile reads; the integer result joins through fp_resmux, the FP result goes down fp_pipe to
    write-back, where fp_wb writes fregfile and fp_csr the flags and FS. A double-word load or store is two word accesses (fp_dwseq)."""
    def move(name, driver_old_sinks_to, new_driver):
        """Net `name` keeps its sinks but gets a new driver; the old driver feeds `driver_old_sinks_to` through a new net `<name>_raw`."""
        n = net[name]
        old = n["driver"]
        n["driver"] = new_driver
        add(f"{name}_raw", n["width"], old, *driver_old_sinks_to)

    def set_sinks(name, sinks):
        net[name]["sinks"] = list(sinks)

    # ---- fetch: the compressed FP loads and stores
    move("fetch_inst", [e("rvc_fp", "word_in")], e("rvc_fp", "word_out"))
    sink("fetch_text", e("rvc_fp", "inst"))
    # ---- decode: the integer decoders see fp_dec's stand-in word
    old = [s for s in net["id_inst"]["sinks"] if s["blockId"] != ids["id_ex"]]
    set_sinks("id_inst", [e("id_ex", "inst_in"), e("fp_dec", "inst")])
    add("dec_inst", 32, e("fp_dec", "dec_inst"), *old)
    # ---- the double-word split: immediate +4 for the second word, an extra hold of the front end
    set_sinks("id_imm", [e("fp_dwseq", "imm_in")])
    add("id_imm_adj", 32, e("fp_dwseq", "imm_out"), e("id_ex", "imm_in"))
    add("id_is_fp", 1, e("fp_dec", "is_fp"), e("fp_hazard", "id_is_fp"))
    add("id_is_dw", 1, e("fp_dec", "is_dw"), e("fp_dwseq", "is_dw"))
    sink("id_valid", e("fp_hazard", "id_valid"), e("fp_dwseq", "valid"))
    sink("id_xcpt", e("fp_dwseq", "xcpt"))
    add("dw_hold", 1, e("fp_dwseq", "hold"), e("fp_hazard", "dw_hold"))
    add("dw_half2", 1, e("fp_dwseq", "half2"), e("fp_hazard", "half2"))
    add("dw_sel_id", 2, e("fp_dwseq", "dwsel"), e("fp_pipe", "dwsel_id"))
    # ---- hazards: the FP wait and the hold join the hazard unit's stall and bubble; the FPU's busy joins md_busy
    set_sinks("stall", [e("fp_hazard", "stall")])
    add("stall_fp", 1, e("fp_hazard", "stall_out"), e("pc", "stall"), e("if_id", "stall"))
    set_sinks("flush_id_ex", [e("fp_hazard", "flush_id_ex")])
    add("flush_id_ex_fp", 1, e("fp_hazard", "flush_out"), e("id_ex", "flush"), e("fp_dwseq", "flush"), e("fp_pipe", "flush_ex"))
    sink("md_stall", e("fp_hazard", "md_stall"), e("fp_dwseq", "stall"), e("fp_pipe", "stall_ex"))
    sink("flush_ex_mem", e("fp_pipe", "flush_mem"))
    sink("flush_mem_wb", e("fp_pipe", "flush_wb"))
    set_sinks("md_busy", [e("fp_or2", "a")])
    add("md_busy_all", 1, e("fp_or2", "y"), e("hazard_unit", "md_busy"))
    add("fp_busy", 1, e("fp_seq", "busy"), e("fp_or2", "b"))
    sink("ex_valid", e("fp_exdec", "valid"), e("fp_hazard", "ex_valid"))
    sink("ex_inst", e("fp_exdec", "inst"), e("fp_hazard", "ex_inst"))
    sink("mem_valid", e("fp_hazard", "mem_valid"))
    sink("mem_inst", e("fp_hazard", "mem_inst"))
    sink("ex_id_xcpt", e("fp_exdec", "xcpt"))
    # ---- execute: the unit, its sequencer, the operands
    add("fp_start", 1, e("fp_seq", "start"), e("fpu", "start"))
    add("fp_is_fpu", 1, e("fp_exdec", "is_fpu"), e("fp_seq", "is_fpu"))
    add("fp_op", 5, e("fp_exdec", "op"), e("fpu", "op"))
    add("fp_dbl", 1, e("fp_exdec", "dbl"), e("fpu", "dbl"))
    add("fp_rm", 3, e("fp_exdec", "rm"), e("fpu", "rm"))
    add("fp_ra1", 5, e("fp_exdec", "ra1"), e("fregfile", "ra1"))
    add("fp_ra2", 5, e("fp_exdec", "ra2"), e("fregfile", "ra2"))
    add("fp_ra3", 5, e("fp_exdec", "ra3"), e("fregfile", "ra3"))
    add("fp_a", 64, e("fregfile", "rdata1"), e("fpu", "a"))
    add("fp_b", 64, e("fregfile", "rdata2"), e("fpu", "b"), e("fp_stmux", "fdata"))
    add("fp_c", 64, e("fregfile", "rdata3"), e("fpu", "c"))
    sink("operand_a", e("fpu", "ia"))
    add("fp_done", 1, e("fpu", "done"), e("fp_seq", "done"))
    add("fp_fres_in", 64, e("fpu", "fres"), e("fp_seq", "fres_in"))
    add("fp_ires_in", 32, e("fpu", "ires"), e("fp_seq", "ires_in"))
    add("fp_flags_in", 5, e("fpu", "flags"), e("fp_seq", "flags_in"))
    add("fp_wrf_in", 1, e("fpu", "wr_f"), e("fp_seq", "wrf_in"))
    # integer results: the execute result is the FPU's for the instructions that write an integer register
    move("ex_alu_y", [e("fp_resmux", "from_alu")], e("fp_resmux", "y"))
    add("fp_ires", 32, e("fp_seq", "ires"), e("fp_resmux", "from_fp"))
    add("fp_int_dest", 1, e("fp_exdec", "int_dest"), e("fp_resmux", "sel"))
    # stores: the data is a floating-point register's word
    set_sinks("operand_b", [s for s in net["operand_b"]["sinks"] if s != e("ex_mem", "store_data_in")] + [e("fp_stmux", "from_core")])
    add("store_data_fp", 32, e("fp_stmux", "y"), e("ex_mem", "store_data_in"))
    add("fp_is_fst", 1, e("fp_exdec", "is_fst"), e("fp_stmux", "is_fst"))
    # alignment trap of a double-word access
    for nm, port in (("ex_xcpt_flag", "xcpt"), ("ex_xcpt_cause", "cause"), ("ex_tval", "tval"), ("ex_memwrite_ok", "memwrite_out")):
        old = net[nm]["driver"]
        net[nm]["driver"] = e("fp_xcpt", port)
        add(f"{nm}_raw", net[nm]["width"], old, e("fp_xcpt", {"xcpt": "xcpt_in", "cause": "cause_in", "tval": "tval_in", "memwrite_out": "memwrite_in"}[port]))
    sink("ex_memwrite", e("fp_xcpt", "is_store"))
    sink("ex_alu_y", e("fp_xcpt", "addr"))
    # ---- the side pipeline and write-back
    add("fp_dwsel_ex", 2, e("fp_pipe", "dwsel_ex"), e("fp_stmux", "dwsel"), e("fp_xcpt", "dwsel"))
    add("fp_fres_ex", 64, e("fp_seq", "fres"), e("fp_pipe", "fres_ex"))
    add("fp_flags_ex", 5, e("fp_seq", "flags"), e("fp_pipe", "flags_ex"))
    add("fp_wrf_ex", 1, e("fp_seq", "wrf"), e("fp_pipe", "wrf_ex"))
    add("fp_dwsel_wb", 2, e("fp_pipe", "dwsel_wb"), e("fp_wb", "dwsel"))
    add("fp_fres_wb", 64, e("fp_pipe", "fres_wb"), e("fp_wb", "fres"))
    add("fp_flags_wb", 5, e("fp_pipe", "flags_wb"), e("fp_wb", "flags"))
    add("fp_wrf_wb", 1, e("fp_pipe", "wrf_wb"), e("fp_wb", "wrf"))
    sink("wb_inst", e("fp_wb", "inst"), e("fp_csr", "inst"))
    sink("retire", e("fp_wb", "commit"))
    sink("wb_mem_rdata", e("fp_wb", "mem_rdata"))
    add("fp_we_lo", 1, e("fp_wb", "we_lo"), e("fregfile", "we_lo"))
    add("fp_we_hi", 1, e("fp_wb", "we_hi"), e("fregfile", "we_hi"))
    add("fp_waddr", 5, e("fp_wb", "waddr"), e("fregfile", "waddr"))
    add("fp_wdata_lo", 32, e("fp_wb", "wdata_lo"), e("fregfile", "wdata_lo"))
    add("fp_wdata_hi", 32, e("fp_wb", "wdata_hi"), e("fregfile", "wdata_hi"))
    add("fp_flags_set", 5, e("fp_wb", "flags_set"), e("fp_csr", "flags_set"))
    add("fp_dirty_set", 1, e("fp_wb", "dirty_set"), e("fp_csr", "dirty_set"))
    # ---- CSRs: fflags, frm, fcsr, mstatus.FS, misa; the legality of accessing them
    sink("wb_csrop", e("fp_csr", "csrop"))
    sink("csr_we", e("fp_csr", "csr_we"))
    sink("csr_nval", e("fp_csr", "nval"))
    move("csr_rdata_hart", [e("fp_csr", "rdata_in")], e("fp_csr", "rdata_out"))
    move("csr_illegal", [e("fp_csr", "illegal_in")], e("fp_csr", "illegal_out"))
    add("fp_fs", 2, e("fp_csr", "fs"), e("fp_dec", "fs"))
    add("fp_frm", 3, e("fp_csr", "frm"), e("fp_dec", "frm"), e("fp_exdec", "frm"))
    # ---- clock and reset
    for b in ("fp_dwseq", "fp_pipe", "fp_seq", "fregfile", "fp_csr", "fpu"):
        clk["sinks"].append(e(b, "clk"))
    for b in ("fp_dwseq", "fp_pipe", "fp_csr"):
        rst["sinks"].append(e(b, "rst"))
    sink("unit_reset", e("fp_seq", "rst"), e("fpu", "rst"))


def wire_bp(nets, net, ids, e, add, sink, clk, rst, fp: bool) -> None:
    """Joins the gshare branch predictor (demos/quad-soc/bpblocks.py) to the core. In the fetch stage gshare_tbl looks up the fetch pc: a predicted-taken
    branch or jump steers the next pc to the predicted target in the same cycle. The prediction travels with the instruction (bp_pipe, stalled and
    flushed like if_id and id_ex) to the execute stage, where bp_resolve compares it with what the branch unit decided: a misprediction redirects as
    the branch unit's redirect did (and flushes the same stages), a correct prediction redirects nothing. The tables learn from every executed branch."""
    stall_net, flush_net = ("stall_fp", "flush_id_ex_fp") if fp else ("stall", "flush_id_ex")
    # the branch unit's decision goes to bp_resolve (and the training), no longer straight to the pc and the hazard unit
    net["redirect"]["sinks"] = [e("bp_resolve", "br_redirect")]
    net["redirect_pc"]["sinks"] = [e("bp_resolve", "br_pc"), e("gshare_tbl", "upd_target")]
    # a misprediction is the redirect of the execute stage; the pc takes it merged with the fetch stage's prediction (the older redirect wins)
    add("mispredict", 1, e("bp_resolve", "redirect"), e("hazard_unit", "redirect"), e("bp_or", "a"), e("bp_mux", "sel"))
    add("mispredict_pc", 32, e("bp_resolve", "redirect_pc"), e("bp_mux", "from_fp"))
    add("pred_redirect", 1, e("gshare_tbl", "pred_redirect"), e("bp_or", "b"))
    add("pred_target", 32, e("gshare_tbl", "pred_target"), e("bp_mux", "from_alu"), e("bp_pipe", "ptarget_if"))
    add("next_redirect", 1, e("bp_or", "y"), e("pc", "redirect"))
    add("next_redirect_pc", 32, e("bp_mux", "y"), e("pc", "redirect_pc"))
    # the lookup at the fetch pc, held off by the same stall as the pc
    sink("pc", e("gshare_tbl", "pc"))
    sink(stall_net, e("gshare_tbl", "stall"), e("bp_pipe", "stall_if"))
    # the carried prediction: stalled and flushed like if_id (fetch to decode) and id_ex (decode to execute)
    add("bp_pt_if", 1, e("gshare_tbl", "pred_taken"), e("bp_pipe", "pt_if"))
    add("bp_pidx_if", 8, e("gshare_tbl", "pred_idx"), e("bp_pipe", "pidx_if"))
    sink("flush_if_id", e("bp_pipe", "flush_if"))
    sink("md_stall", e("bp_pipe", "stall_id"))
    sink(flush_net, e("bp_pipe", "flush_id"))
    # the execute stage's facts and the carried prediction, for the resolution
    sink("ex_pcsel", e("bp_resolve", "pcsel"))
    sink("ex_valid", e("bp_resolve", "valid"))
    sink("ex_pc_plus4", e("bp_resolve", "pc_plus4"))
    add("bp_pt_ex", 1, e("bp_pipe", "pt_ex"), e("bp_resolve", "pt"))
    add("bp_ptarget_ex", 32, e("bp_pipe", "ptarget_ex"), e("bp_resolve", "ptarget"))
    add("bp_pidx_ex", 8, e("bp_pipe", "pidx_ex"), e("bp_resolve", "pidx"))
    # the training of the tables from every executed branch or jump
    add("bp_upd_en", 1, e("bp_resolve", "upd_en"), e("gshare_tbl", "upd_en"))
    add("bp_upd_idx", 8, e("bp_resolve", "upd_idx"), e("gshare_tbl", "upd_idx"))
    add("bp_upd_taken", 1, e("bp_resolve", "upd_taken"), e("gshare_tbl", "upd_taken"))
    add("bp_upd_cond", 1, e("bp_resolve", "upd_cond"), e("gshare_tbl", "upd_cond"))
    add("bp_upd_jump", 1, e("bp_resolve", "upd_jump"), e("gshare_tbl", "upd_jump"))
    sink("ex_pc", e("gshare_tbl", "upd_pc"))
    for b in ("gshare_tbl", "bp_pipe"):
        clk["sinks"].append(e(b, "clk")); rst["sinks"].append(e(b, "rst"))


def design(mem: bool = False, fp: bool = False, bp: bool = False, pmp: bool = False, sext: bool = False) -> dict:
    """mem=True: the core of the memory-system SoC: three more top-level outputs for it (fetch_need_hi: the fetched instruction continues into the
    next word; fence_i: a fence.i retires; mem_is_amo: the memory-stage instruction is atomic) and the two small blocks that make them."""
    base = json.loads((ROOT / "demos" / "quad-soc" / "design-core.json").read_text())
    by_name = {b["name"]: b for b in base["blocks"]}
    gone = {by_name[n]["id"] for n in REMOVE}
    blocks = [b for b in base["blocks"] if b["id"] not in gone and b["name"] not in ("sys_decode", "ex_xcpt")]
    blocks = [copy.deepcopy(B.KILL_GATE) if b["name"] == "kill_gate" else b for b in blocks]
    copies = {}
    for blk in (B.PA_MUX, B.PERM_CHECK, B.XFAULT):
        for s in ("ilo", "ihi", "d"):
            copies[(blk["name"], s)] = inst(blk, s)
    pmp_copies = [inst(B.PMP_CHECK, s) for s in ("ilo", "ihi", "d", "ptw")] + [inst(FB.FP_OR2, "pmp_" + s) for s in ("d",)] if pmp else []
    new = [B.PMP_REGS16 if pmp else B.PMP_REGS, *([B.PMP_K] if pmp else []), *pmp_copies, B.SYS_DECODE, B.EX_XCPT, B.CSR_SEL2, B.CSR_HW, B.CSR_ALU, B.IRQ_SELECT, B.MSTATUS_REG, B.TRAP_UNIT, B.CSR_MREGS, B.CSR_SREGS,
           B.COUNTERS, ({**copy.deepcopy(MB.MIP_MERGE_S), "id": B.MIP_MERGE["id"], "name": B.MIP_MERGE["name"]} if sext else B.MIP_MERGE), B.CSR_RMUX, B.STATUS_WE, B.SATP_SPLIT, B.XLATE_ON, B.DKIND, B.DFAULT_GATE, ({**copy.deepcopy(B.IFAULT_PMP), "id": B.IFAULT["id"], "name": B.IFAULT["name"], "moduleName": B.IFAULT["moduleName"]} if pmp else B.IFAULT), B.MMU_CTL, *copies.values(), *([MB.NEED_HI_GEN, MB.FENCEI_GATE] if mem else []), *(FB.BLOCKS + [fpu_block()] if fp else []), *(BPB.BLOCKS if bp else [])]
    blocks += new
    ids = {b["name"]: b["id"] for b in blocks}
    nets = []
    for n in base["nets"]:
        n = copy.deepcopy(n)
        n["sinks"] = [s for s in n["sinks"] if s["blockId"] not in gone]
        if n["driver"]["blockId"] in gone:
            n["driver"] = None                          # re-driven below, or dropped when nothing takes it
        nets.append(n)
    net = {n["name"]: n for n in nets}
    tops = list(base["topLevelPorts"])
    tops = [{**p} for p in tops]

    def e(block: str | None, p: str) -> dict:
        return {"blockId": None if block is None else ids[block], "portId": p if block is None else f"p_{p}"}

    def add(name: str, width: int, drv: dict, *sinks: dict) -> None:
        if name in net:
            raise SystemExit(f"net {name} exists")
        n = {"id": f"n_s{len(nets) + 1:03d}", "name": name, "width": width, "driver": drv, "sinks": list(sinks),
             "kind": "bus" if width > 1 else "wire", "pipelineStage": 0}
        nets.append(n)
        net[name] = n

    def sink(name: str, *sinks: dict) -> None:
        net[name]["sinks"].extend(sinks)

    def top(name: str, direction: str, width: int, role: str = "data") -> dict:
        tops.append({"id": f"t_{name}", "name": name, "direction": direction, "width": width, "role": role, "blockId": None})
        return {"blockId": None, "portId": f"t_{name}"}

    clk, rst = net["clock"], net["reset"]
    for b in ("mstatus_reg", "csr_mregs", "csr_sregs", "counters"):
        clk["sinks"].append(e(b, "clk"))
        rst["sinks"].append(e(b, "rst"))

    # ---------------------------------------------------------------- decode and execute: the regenerated blocks keep their nets
    # sys_decode and ex_xcpt keep their ids and port ids, so their old nets still reach them; only their new ports are wired below

    # ---------------------------------------------------------------- privilege, mstatus, satp
    add("priv", 2, e("mstatus_reg", "priv"), e("sys_decode", "priv"), e("csr_sel2", "priv"), e("csr_hw", "priv"), e("trap_unit", "priv"), *([e("pmp_check_ilo", "priv"), e("pmp_check_ihi", "priv")] if pmp else []),
        e("irq_select", "priv"), e("xlate_on", "priv"))
    add("mstatus", W, e("mstatus_reg", "mstatus"), e("csr_rmux", "mstatus"))
    add("st_mie", 1, e("mstatus_reg", "mie"), e("irq_select", "mstatus_mie"))
    add("st_sie", 1, e("mstatus_reg", "sie"), e("irq_select", "mstatus_sie"))
    add("st_mprv", 1, e("mstatus_reg", "mprv"), e("xlate_on", "mprv"))
    add("st_mpp", 2, e("mstatus_reg", "mpp"), e("xlate_on", "mpp"))
    add("st_sum", 1, e("mstatus_reg", "sum"), *[e(f"perm_check_{s}", "sum") for s in ("ilo", "ihi", "d")])
    add("st_mxr", 1, e("mstatus_reg", "mxr"), *[e(f"perm_check_{s}", "mxr") for s in ("ilo", "ihi", "d")])
    add("st_tvm", 1, e("mstatus_reg", "tvm"), e("csr_sel2", "tvm"), e("trap_unit", "tvm"))
    add("st_tsr", 1, e("mstatus_reg", "tsr"), e("trap_unit", "tsr"))
    add("satp", W, e("csr_sregs", "satp"), e("csr_rmux", "satp"), e("satp_split", "satp"))
    add("satp_mode", 1, e("satp_split", "mode"), e("xlate_on", "satp_mode"))
    add("satp_ppn", 22, e("satp_split", "ppn"), top("satp_ppn", "out", 22, "addr"))

    # ---------------------------------------------------------------- write-back: CSR access, traps
    sink("wb_inst", e("csr_sel2", "inst"), e("csr_hw", "inst"), e("trap_unit", "inst"), *([e("pmp_regs16", "inst")] if pmp else []))
    sink("wb_csrop", e("csr_sel2", "csrop"), e("csr_hw", "csrop"), e("trap_unit", "csrop"), e("csr_alu", "csrop"))
    for p, n in (("valid", "wb_valid"), ("xcpt", "wb_xcpt"), ("irq", "wb_irq"), ("cause", "wb_cause"), ("pc", "wb_pc"),
                 ("tval", "wb_tval"), ("is_mret", "wb_is_mret")):
        sink(n, e("trap_unit", p))
    sink("wb_csr_wdata", e("csr_alu", "src"))
    # csr_hw maps the hard-wired performance/endianness CSRs (mstatush, mhpmevent*, mhpmcounter*) onto number 44 after the decoder
    add("csr_sel", 6, e("csr_sel2", "sel"), e("csr_hw", "sel_in"))
    add("csr_sel_hw", 6, e("csr_hw", "sel_out"), e("csr_rmux", "sel"), e("csr_mregs", "sel"), e("csr_sregs", "sel"), e("status_we", "sel"))
    add("csr_illegal", 1, e("csr_sel2", "illegal"), e("csr_hw", "ill_in"))
    add("csr_illegal_hw", 1, e("csr_hw", "ill_out"), e("trap_unit", "illegal_csr"))
    net["csr_rdata_hart"]["driver"] = e("csr_rmux", "rdata")
    sink("csr_rdata_hart", e("csr_alu", "old"))
    add("csr_nval", W, e("csr_alu", "nval"), e("csr_mregs", "nval"), e("csr_sregs", "nval"), e("mstatus_reg", "wdata"))
    add("csr_we", 1, e("trap_unit", "csr_we"), e("csr_mregs", "we"), e("csr_sregs", "we"), e("status_we", "csr_we"))
    add("we_mstatus", 1, e("status_we", "we_m"), e("mstatus_reg", "we_m"))
    add("we_sstatus", 1, e("status_we", "we_s"), e("mstatus_reg", "we_s"))
    # the program counter refetches after a CSR write (redirect); everything that is killed takes kill (traps, mret, sret)
    # redirect (a trap, mret, sret or a CSR refetch) flushes the younger instructions and kills their memory accesses, as before;
    # kill (a trap, mret or sret only) cancels the register write of the instruction in write-back itself (kill_gate.kill_wb)
    refetch_sinks = [e("hazard_unit", "wb_redirect"), e("md_reset", "kill"), e("amo_core", "kill"), e("amo_active", "kill"),
                      e("mem_req", "kill"), e("kill_gate", "kill_mem"), {"blockId": None, "portId": "t_mem_kill"}]
    kill_sinks = [e("kill_gate", "kill_wb")]
    net["wb_redirect"]["sinks"] = [e("pc", "trap_redirect")] + refetch_sinks
    net["wb_redirect"]["driver"] = e("trap_unit", "redirect")
    # the same redirect leaves the core too: the tile cancels the page walk of a squashed instruction with it
    net["wb_redirect"]["sinks"].append(top("wb_redirect", "out", 1, "control"))
    kill_net = {"id": "n_skill", "name": "wb_kill", "width": 1, "driver": e("trap_unit", "kill"), "sinks": kill_sinks,
                "kind": "wire", "pipelineStage": 0}
    nets.append(kill_net); net["wb_kill"] = kill_net
    net["wb_redirect_pc"]["driver"] = e("trap_unit", "redirect_pc")
    add("trap_m", 1, e("trap_unit", "trap_m"), e("mstatus_reg", "trap_m"), e("csr_mregs", "trap_m"))
    add("trap_s", 1, e("trap_unit", "trap_s"), e("mstatus_reg", "trap_s"), e("csr_sregs", "trap_s"))
    add("do_mret", 1, e("trap_unit", "mret"), e("mstatus_reg", "mret"))
    add("do_sret", 1, e("trap_unit", "sret"), e("mstatus_reg", "sret"))
    add("trap_epc", W, e("trap_unit", "epc"), e("csr_mregs", "epc"), e("csr_sregs", "epc"))
    add("trap_cause", W, e("trap_unit", "cause_val"), e("csr_mregs", "cause_val"), e("csr_sregs", "cause_val"))
    add("trap_tval", W, e("trap_unit", "tval_out"), e("csr_mregs", "tval"), e("csr_sregs", "tval"))
    add("retire", 1, e("trap_unit", "retire"), e("counters", "retire"))
    # the counters take CSR writes (mcycle, minstret) in write-back: the same we, sel and nval as the other CSR blocks
    if pmp:   # sixteen entries with enforcement (PMP checks on the fetch, data and page-walk physical addresses)
        sink("csr_we", e("counters", "we"), e("pmp_regs16", "we"))
        sink("csr_sel_hw", e("pmp_regs16", "sel"))
        sink("csr_nval", e("pmp_regs16", "nval"))
        clk["sinks"].append(e("pmp_regs16", "clk")); rst["sinks"].append(e("pmp_regs16", "rst"))
        add("pmp_rdata", W, e("pmp_regs16", "rdata"), e("csr_rmux", "pmpcfg0"), e("csr_rmux", "pmpaddr0"))
        add("pmp_cfg", 128, e("pmp_regs16", "cfg_all"), *[e(f"pmp_check_{s}", "cfg_all") for s in ("ilo", "ihi", "d", "ptw")])
        add("pmp_addr", 512, e("pmp_regs16", "addr_all"), *[e(f"pmp_check_{s}", "addr_all") for s in ("ilo", "ihi", "d", "ptw")])
        add("pmp_kind_f", 2, e("pmp_k", "kind_f"), e("pmp_check_ilo", "kind"), e("pmp_check_ihi", "kind"))
        add("pmp_kind_d", 2, e("pmp_k", "kind_d"), e("pmp_check_d", "kind"))
        add("pmp_kind_l", 2, e("pmp_k", "kind_l"), e("pmp_check_ptw", "kind"))
        add("pmp_priv_s", 2, e("pmp_k", "priv_s"), e("pmp_check_ptw", "priv"))
        add("pmp_one", 1, e("pmp_k", "one"), e("pmp_check_ilo", "en"), e("pmp_check_ihi", "en"))
        add("ptw_pmp_addr", W, top("ptw_addr", "in", W, "addr"), e("pmp_check_ptw", "pa"))
        add("ptw_pmp_req", 1, top("ptw_req", "in", 1, "control"), e("pmp_check_ptw", "en"))
        add("ptw_pmp_deny", 1, e("pmp_check_ptw", "deny"), top("ptw_deny", "out", 1, "control"))
    else:
        sink("csr_we", e("counters", "we"), e("pmp_regs", "we"))
        sink("csr_sel", e("pmp_regs", "sel"))
        sink("csr_nval", e("pmp_regs", "nval"))
        clk["sinks"].append(e("pmp_regs", "clk")); rst["sinks"].append(e("pmp_regs", "rst"))
        add("pmpcfg0", W, e("pmp_regs", "pmpcfg0"), e("csr_rmux", "pmpcfg0"))
        add("pmpaddr0", W, e("pmp_regs", "pmpaddr0"), e("csr_rmux", "pmpaddr0"))
    sink("csr_sel", e("counters", "sel"))
    sink("csr_nval", e("counters", "nval"))
    add("sfence", 1, e("trap_unit", "sfence"), top("sfence", "out", 1, "control"))
    for name, w, dests in (("mtvec", W, ("trap_unit", "csr_rmux")), ("mepc", W, ("trap_unit", "csr_rmux")),
                           ("mscratch", W, ("csr_rmux",)), ("mcause", W, ("csr_rmux",)), ("mtval", W, ("csr_rmux",)),
                           ("mie", 12, ("csr_rmux", "irq_select")), ("medeleg", 16, ("csr_rmux", "trap_unit")),
                           ("mideleg", 12, ("csr_rmux", "trap_unit", "irq_select")), ("mcounteren", 3, ("csr_rmux", "csr_sel2"))):
        add(f"r_{name}", w, e("csr_mregs", name), *[e(d, name) for d in dests])
    add("r_mip_sw", 12, e("csr_mregs", "mip_sw"), e("mip_merge", "mip_sw"))
    for name, dests in (("stvec", ("trap_unit", "csr_rmux")), ("sepc", ("trap_unit", "csr_rmux")), ("sscratch", ("csr_rmux",)),
                        ("scause", ("csr_rmux",)), ("stval", ("csr_rmux",))):
        add(f"r_{name}", W, e("csr_sregs", name), *[e(d, name) for d in dests])
    add("r_scounteren", 3, e("csr_sregs", "scounteren"), e("csr_rmux", "scounteren"), e("csr_sel2", "scounteren"))
    add("mcycle", 64, e("counters", "mcycle"), e("csr_rmux", "mcycle"))
    add("minstret", 64, e("counters", "minstret"), e("csr_rmux", "minstret"))
    add("mtime", 64, top("mtime", "in", 64), e("csr_rmux", "mtime"))
    sink("hartid", e("csr_rmux", "hartid"))

    # ---------------------------------------------------------------- interrupts
    for line, p in (("ext_meip", "meip"), ("ext_mtip", "mtip"), ("ext_msip", "msip")):
        sink(line, e("mip_merge", p))
    if sext:   # the supervisor external interrupt (PLIC context 2h+1) is bit 9 of mip next to the software-writable bit
        add("ext_seip", 1, top("ext_seip", "in", 1, "control"), e("mip_merge", "seip"))
    add("mip", 12, e("mip_merge", "mip"), e("csr_rmux", "mip"), e("irq_select", "mip"))
    net["irq_is_pending"]["driver"] = e("irq_select", "pending")
    net["irq_pending_cause"]["driver"] = e("irq_select", "cause")

    # ---------------------------------------------------------------- fetch through the MMU
    add("xlate_i", 1, e("xlate_on", "xlate_i"), e("pa_mux_ilo", "xlate"), e("pa_mux_ihi", "xlate"), e("ifault", "xlate"),
        e("mmu_ctl", "xlate_i"))
    add("xlate_d", 1, e("xlate_on", "xlate_d"), e("pa_mux_d", "xlate"), e("mmu_ctl", "xlate_d"), e("dfault_gate", "xlate"))
    add("dpriv", 2, e("xlate_on", "dpriv"), e("perm_check_d", "priv"), *([e("pmp_check_d", "priv")] if pmp else []))
    sink("priv", e("perm_check_ilo", "priv"), e("perm_check_ihi", "priv"))
    add("kind_i", 2, e("xlate_on", "kind_i"), e("perm_check_ilo", "kind"), e("perm_check_ihi", "kind"))
    sink("pc", e("pa_mux_ilo", "va"), e("ifault", "pc"), e("mmu_ctl", "pc"))
    add("fetch_pa_lo", W, e("pa_mux_ilo", "pa"), top("fetch_pa_lo", "out", W, "addr"), *([e("pmp_check_ilo", "pa")] if pmp else []))
    sink("fetch_hi_addr", e("pa_mux_ihi", "va"), e("mmu_ctl", "hi_addr"))
    add("fetch_pa_hi", W, e("pa_mux_ihi", "pa"), top("fetch_pa_hi", "out", W, "addr"), *([e("pmp_check_ihi", "pa")] if pmp else []))
    net["fetched_inst"]["driver"] = top("inst_lo", "in", W)
    sink("fetched_inst", e("ifault", "word_lo"))
    net["fetched_hi"]["driver"] = top("inst_hi", "in", W)
    # the aligner's outputs go through ifault
    net["fetch_text"]["driver"] = e("ifault", "inst_out")
    net["fetch_is16"]["driver"] = e("ifault", "is16_out")
    add("aligned_inst", W, e("fetch_align", "inst"), e("ifault", "inst"))
    add("aligned_is16", 1, e("fetch_align", "is16"), e("ifault", "is16"))
    # the three lookups' virtual addresses go out to the TLBs (outside the core) and into the fault checks
    sink("pc", e("xfault_ilo", "va"), top("va_ilo", "out", W, "addr"))
    sink("fetch_hi_addr", e("xfault_ihi", "va"), top("va_ihi", "out", W, "addr"))
    for s in ("ilo", "ihi", "d"):
        add(f"tlb_{s}_hit", 1, top(f"tlb_{s}_hit", "in", 1, "control"), e(f"xfault_{s}", "hit"))
        add(f"tlb_{s}_ppa", 20, top(f"tlb_{s}_ppa", "in", 20, "addr"), e(f"pa_mux_{s}", "ppa"))
        add(f"tlb_{s}_flags", 8, top(f"tlb_{s}_flags", "in", 8, "control"), e(f"perm_check_{s}", "flags"))
        add(f"perm_{s}", 1, e(f"perm_check_{s}", "fault"), e(f"xfault_{s}", "perm_fault"))
    add("ptw_busy", 1, top("ptw_busy", "in", 1, "control"), e("mmu_ctl", "ptw_busy"))
    add("ptw_fault", 1, top("ptw_fault", "in", 1, "control"), *[e(f"xfault_{s}", "wfault") for s in ("ilo", "ihi", "d")])
    add("ptw_fault_access", 1, top("ptw_fault_access", "in", 1, "control"), *[e(f"xfault_{s}", "waccess") for s in ("ilo", "ihi", "d")])
    add("ptw_fault_vpn", 20, top("ptw_fault_vpn", "in", 20, "addr"), *[e(f"xfault_{s}", "wvpn") for s in ("ilo", "ihi", "d")])
    add("ilo_pf", 1, e("xfault_ilo", "pf"), e("ifault", "lo_pf"))
    add("ilo_af", 1, e("xfault_ilo", "af"), e("ifault", "lo_af"))
    if pmp:
        add("ilo_pmp", 1, e("pmp_check_ilo", "deny"), e("ifault", "pmp_lo"))
    add("ihi_pf", 1, e("xfault_ihi", "pf"), e("ifault", "hi_pf"))
    add("ihi_af", 1, e("xfault_ihi", "af"), e("ifault", "hi_af"))
    if pmp:
        add("ihi_pmp", 1, e("pmp_check_ihi", "deny"), e("ifault", "pmp_hi"))
    add("ilo_miss", 1, e("xfault_ilo", "miss"), e("mmu_ctl", "lo_miss"))
    add("ihi_miss", 1, e("xfault_ihi", "miss"), e("mmu_ctl", "hi_miss"))
    add("d_miss", 1, e("xfault_d", "miss"), e("mmu_ctl", "d_miss"))

    # ---------------------------------------------------------------- data through the MMU (execute stage)
    sink("ex_valid", e("dkind", "valid"))
    sink("ex_memsrc", e("dkind", "memsrc"))
    sink("ex_memwrite", e("dkind", "memwrite"))
    sink("ex_is_amo", e("dkind", "is_amo"))
    sink("ex_amo_op", e("dkind", "amo_op"))
    add("d_access", 1, e("dkind", "access"), e("mmu_ctl", "d_access"), e("dfault_gate", "access"), *([e("pmp_check_d", "en")] if pmp else []))
    add("d_store", 1, e("dkind", "store"), e("ex_xcpt", "d_store"), *([e("pmp_k", "store")] if pmp else []))
    add("d_kind", 2, e("dkind", "kind"), e("perm_check_d", "kind"))
    # a translation fault counts only for an instruction that accesses memory (an ALU result that lands on a protected page is no fault)
    add("d_pf_raw", 1, e("xfault_d", "pf"), e("dfault_gate", "pf"))
    add("d_af_raw", 1, e("xfault_d", "af"), e("dfault_gate", "af"))
    add("d_pf", 1, e("dfault_gate", "pf_o"), e("ex_xcpt", "d_pf"))
    if pmp:
        add("d_af", 1, e("dfault_gate", "af_o"), e("fp_or2_pmp_d", "a"))
        add("d_pmp", 1, e("pmp_check_d", "deny"), e("fp_or2_pmp_d", "b"))
        add("d_af_or", 1, e("fp_or2_pmp_d", "y"), e("ex_xcpt", "d_af"))
    else:
        add("d_af", 1, e("dfault_gate", "af_o"), e("ex_xcpt", "d_af"))
    # ex_mem takes the physical address; everything else keeps the virtual one
    alu = net["ex_alu_y"]
    alu["sinks"] = [s for s in alu["sinks"] if s != e("ex_mem", "alu_y_in")] + [e("pa_mux_d", "va"), e("mmu_ctl", "d_va"),
                                                                                      e("xfault_d", "va"), top("va_d", "out", W, "addr")]
    add("ex_pa", W, e("pa_mux_d", "pa"), e("ex_mem", "alu_y_in"), *([e("pmp_check_d", "pa")] if pmp else []))
    sink("fetched_inst", e("mmu_ctl", "word_lo"))
    add("mmu_stall", 1, e("mmu_ctl", "stall"), top("mmu_stall", "out", 1, "control"))
    add("walk_start", 1, e("mmu_ctl", "walk_start"), top("walk_start", "out", 1, "control"))
    add("walk_va", W, e("mmu_ctl", "walk_va"), top("walk_va", "out", W, "addr"))
    if mem:
        sink("pc", e("need_hi_gen", "pc"))
        sink("fetched_inst", e("need_hi_gen", "word_lo"))
        add("fetch_need_hi", 1, e("need_hi_gen", "need_hi"), top("fetch_need_hi", "out", 1, "control"))
        sink("wb_valid", e("fencei_gate", "valid"))
        sink("wb_csrop", e("fencei_gate", "csrop"))
        sink("trap_m", e("fencei_gate", "trap_m"))
        sink("trap_s", e("fencei_gate", "trap_s"))
        add("fence_i", 1, e("fencei_gate", "fence_i"), top("fence_i", "out", 1, "control"))
        sink("mem_is_amo", top("mem_is_amo", "out", 1, "control"))
    if fp:
        wire_fp(nets, net, ids, e, add, sink, clk, rst)
    if bp:
        wire_bp(nets, net, ids, e, add, sink, clk, rst, fp)
    orphans = [n["name"] for n in nets if n["driver"] is None and n["sinks"]]
    if orphans:
        raise SystemExit(f"nets that lost their driver: {orphans}")
    nets = [n for n in nets if n["driver"] is not None]
    return {**{k: v for k, v in base.items() if k not in ("blocks", "nets", "topLevelPorts")}, "id": "rv-core-s",
            "name": "RV32IMAC core with supervisor mode and an Sv32 MMU (combinational half; TLBs and walker in the tile)",
            "blocks": blocks, "nets": nets, "topLevelPorts": tops}


if __name__ == "__main__":
    mem, fp, bp, pmp, sext = "--mem" in sys.argv, "--fp" in sys.argv, "--bp" in sys.argv, "--pmp" in sys.argv, "--sext" in sys.argv
    d = design(mem, fp, bp, pmp, sext)
    (HERE / ("design-core" + ("-mem" if mem else "") + ("-fp" if fp else "") + ("-bp" if bp else "") + ("-pmp" if pmp else "") + ("-sext" if sext else "") + ".json")).write_text(json.dumps(d, indent=1) + "\n")
    print(len(d["blocks"]), "blocks", len(d["nets"]), "nets")
