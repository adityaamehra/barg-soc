"""Build the SIMT GPU core (v0) as a BARG design: blocks, nets and top-level ports, written to design.json.

    python3 demos/simt-gpu/build.py            # writes design.json and the two pipeline-register golden models

The architecture is in README.md; the instruction set in ISA.md; one golden model per block in golden/. This file is the design:
edit it, not the JSON. Like the RISC-V demos, nothing in packages/ knows what a GPU is; these are ordinary blocks.

Pipeline (one instruction in flight per warp, so no scoreboard, no forwarding and no flush):
  S  warp_sched picks a ready warp; warp_table gives its pc; imem is read (synchronous)          -> sf_reg
  D  decode, imm_gen, regfile read (asynchronous) through operand                                  -> dx_reg
  X  valu, vmul, vdiv, branch_unit, vote_shfl, simt_ctrl, tensor_unit, csr, lsu (with the banks); wb_mux writes the register
     file, and warp_table, ipdom, barrier_unit and tensor_unit update, all at the edge where the instruction leaves X
     (pipe_ctrl's advance). Only the divider and the load-store unit hold the pipeline (pipe_ctrl's stall).
Lane i of every 128-bit bus is bits 32i+31..32i.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
_spec = importlib.util.spec_from_file_location("single_cycle_build", HERE.parent / "rv32i-single-cycle" / "build.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)
port, encoding, block = sc.port, sc.encoding, sc.block

W, V = 32, 128            # a word; four lanes of words
LANES = "Lane i of a 128-bit bus is bits 32i+31..32i (four lanes)."

# --------------------------------------------------------------------------- #
# Encodings (declared on decode's outputs, inherited along the nets)
# --------------------------------------------------------------------------- #

UNIT = encoding("Which execution unit an instruction uses.", {
    "000": "ALU: the arithmetic unit (also used by jumps and branches)", "001": "MUL: the multiplier",
    "010": "DIV: the iterative divider", "011": "LSU: the load-store unit", "100": "SIMT: the SIMT control instructions",
    "101": "TENSOR: the tensor unit", "110": "CSR: a CSR read", "111": "NONE: no unit (fence, or an illegal instruction)"})
ALU_OP = encoding("The arithmetic unit's operation on its two operands x and z (shifts use z bits 4:0).", {
    "0000": "ADD: x + z", "0001": "SUB: x - z", "0010": "SLL: x shifted left", "0011": "SLT: 1 when x < z signed, else 0",
    "0100": "SLTU: 1 when x < z unsigned, else 0", "0101": "XOR", "0110": "SRL: x shifted right, zeros in",
    "0111": "SRA: x shifted right, copies of bit 31 in", "1000": "OR", "1001": "AND", "1010": "PASS_B: z",
    "1011": "reserved: 0", "1100": "reserved: 0", "1101": "reserved: 0", "1110": "reserved: 0", "1111": "reserved: 0"})
WB_SRC = encoding("Which result is written back to the register file.", {
    "000": "ALU: the arithmetic unit's result", "001": "MUL: the multiplier's", "010": "DIV: the divider's",
    "011": "LOAD: the load-store unit's loaded value", "100": "SIMT: the vote / shuffle result",
    "101": "TENSOR: the tensor unit's accumulator column", "110": "CSR: the CSR value", "111": "LINK: pc + 4 in every lane"})
CTRL = encoding("How the next pc is chosen.", {
    "00": "NONE: pc + 4", "01": "BRANCH: pc + imm when the branch is taken, else pc + 4", "10": "JAL: pc + imm",
    "11": "JALR: (rs1 + imm) with bit 0 cleared"})
BR_OP = encoding("The branch comparison of rs1 with rs2 (the instruction's funct3).", {
    "000": "BEQ: equal", "001": "BNE: not equal", "010": "never", "011": "never", "100": "BLT: signed less",
    "101": "BGE: signed greater or equal", "110": "BLTU: unsigned less", "111": "BGEU: unsigned greater or equal"})
SIMT_OP = encoding("The SIMT instruction (funct3 of the custom-0 opcode).", {
    "000": "TMC: set the thread mask", "001": "WSPAWN: start warps", "010": "SPLIT: diverge on a predicate",
    "011": "JOIN: reconverge", "100": "BAR: wait at a barrier", "101": "VOTE", "110": "SHFL: shuffle", "111": "none"})
TENSOR_OP = encoding("The tensor instruction (funct3 bits 1:0 of the custom-1 opcode).", {
    "00": "MMA_I8: accumulate A x B", "01": "MMA_LD: read an accumulator column", "10": "MMA_ST: write an accumulator column",
    "11": "MMA_ZERO: clear the accumulator"})
ENC = {"unit": UNIT, "alu_op": ALU_OP, "wb_src": WB_SRC, "ctrl": CTRL, "br_op": BR_OP, "simt_op": SIMT_OP,
       "tensor_op": TENSOR_OP, "immsel": sc.IMMSEL}


def clocked(*ports):
    return [port("p_clk", "clk", "in", 1, "clock"), port("p_rst", "rst", "in", 1, "reset"), *ports]


def i(name, width, role=None, enc=None):
    return port(f"p_{name}", name, "in", width, role, ENC[enc] if enc else None)


def o(name, width, role=None, enc=None):
    return port(f"p_{name}", name, "out", width, role, ENC[enc] if enc else None)


# --------------------------------------------------------------------------- #
# Pipeline registers (their golden models are written from these field lists)
# --------------------------------------------------------------------------- #

SF_FIELDS = [("valid", 1, "valid", None), ("wid", 2, "addr", None), ("pc", W, "addr", None), ("tmask", 4, "control", None)]
DX_FIELDS = SF_FIELDS + [
    ("rd", 5, "addr", None), ("unit", 3, "control", "unit"), ("alu_op", 4, "control", "alu_op"), ("a_sel", 1, "control", None),
    ("b_sel", 1, "control", None), ("wb_src", 3, "control", "wb_src"), ("regwrite", 1, "control", None),
    ("ctrl", 2, "control", "ctrl"), ("br_op", 3, "control", "br_op"), ("mem_store", 1, "control", None),
    ("mem_size", 3, "control", None), ("md_op", 2, "control", None), ("simt_op", 3, "control", "simt_op"),
    ("simt_mode", 2, "control", None), ("tensor_op", 2, "control", "tensor_op"), ("csr_addr", 12, "addr", None),
    ("illegal", 1, "control", None), ("imm", W, "data", None), ("a", V, "data", None), ("b", V, "data", None)]


def pipe_register(bid, name, title, fields):
    ports = clocked(i("clear", 1, "control"), i("hold", 1, "control"))
    ports += [port(f"p_{f}_in", f"{f}_in", "in", w, role) for f, w, role, _ in fields]
    ports += [port(f"p_{f}_out", f"{f}_out", "out", w, role, ENC[e] if e else None) for f, w, role, e in fields]
    return block(bid, name, f"""
        {title}. Every output <f>_out shows the value its input <f>_in had at the last rising clock edge at which the register
        loaded; no output depends combinationally on any input. On each rising edge: when rst is 1 or clear is 1 every field
        becomes 0 (so valid_out becomes 0: a bubble); otherwise when hold is 1 every field keeps its value; otherwise every
        field takes its input. The fields: {", ".join(f"{f} ({w} bits)" for f, w, _, _ in fields)}.
    """, ports, reset_style="sync", latency=1)


SF_REG = pipe_register("b_sf_reg", "sf_reg", "S/D pipeline register, between the warp scheduler and the decoder", SF_FIELDS)
DX_REG = pipe_register("b_dx_reg", "dx_reg", "D/X pipeline register, between the decoder and the execution units", DX_FIELDS)


def write_pipe_golden(name, fields):
    names = [f for f, _, _, _ in fields]
    (HERE / "golden" / f"{name}.py").write_text(f'''"""Golden model of the pipeline register `{name}` (written by build.py from its field list).

Every output <f>_out shows the value its input <f>_in had at the last rising edge at which the register loaded. At each rising
edge: rst or clear sets every field to 0 (valid becomes 0, a bubble); otherwise when hold is 1 every field keeps its value;
otherwise every field takes its input. Before the first reset every field is unknown.
"""

FIELDS = {names!r}


class PipeReg:
    def __init__(self):
        self.state = None

    def outputs(self, i):
        return {{f + "_out": None if self.state is None else self.state[f] for f in FIELDS}}

    def edge(self, i):
        if i["rst"] & 1 or i["clear"] & 1:
            self.state = {{f: 0 for f in FIELDS}}
        elif self.state is not None and not i["hold"] & 1:
            self.state = {{f: i[f + "_in"] for f in FIELDS}}


def golden_{name}(trace):
    m, out = PipeReg(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out
''', encoding="utf-8")


# --------------------------------------------------------------------------- #
# Front end: S stage
# --------------------------------------------------------------------------- #

WARP_SCHED = block("b_warp_sched", "warp_sched", """
    Warp scheduler, round robin. A warp is ready when it is active, has no instruction in flight and is not waiting at a
    barrier: ready = active & ~inflight & ~waiting (bit w for warp w). When enable is 1 and some warp is ready, fire = 1 and
    fwid is the first ready warp in the order ptr+1, ptr+2, ptr+3, ptr+4 (modulo 4), where ptr is a 2-bit register holding
    the warp chosen last; otherwise fire = 0 and fwid = 0. fire and fwid follow the inputs and ptr at once (combinationally).
    On each rising edge: when rst or start is 1, ptr becomes 3 (so warp 0 is chosen first); otherwise when fire is 1, ptr
    becomes fwid; otherwise ptr keeps its value.
""", clocked(i("start", 1, "control"), i("enable", 1, "control"), i("active", 4, "control"), i("inflight", 4, "control"),
             i("waiting", 4, "control"), o("fire", 1, "valid"), o("fwid", 2, "addr")), reset_style="sync", latency=0)

WARP_TABLE = block("b_warp_table", "warp_table", """
    Per-warp state for 4 warps: a 32-bit pc, a 4-bit thread mask and an in-flight bit each. A warp is active when its mask is
    not 0. Outputs, combinational from the state and fwid: sel_pc and sel_tmask are warp fwid's pc and mask; active and
    inflight have one bit per warp (bit w for warp w); busy is 1 when any warp is active or in flight.
    On each rising edge, the first of these that applies:
    (1) rst is 1: every pc, mask and in-flight bit becomes 0.
    (2) start is 1: warp 0 gets pc = start_pc, mask 0001; warps 1 to 3 get pc 0 and mask 0000; every in-flight bit becomes 0.
    (3) otherwise three independent events apply, all computed from the values before this edge (a later event overrides an
    earlier one only on the field it names):
    - commit (when commit is 1): warp cwid gets pc = c_pc, mask = c_tmask and in-flight = 0.
    - fire (when fire is 1): warp fwid's in-flight bit becomes 1. It does not depend on spawn_mask and does not stop a spawn.
    - spawn: each warp w with spawn_mask bit w = 1 whose mask was 0000 and whose in-flight bit was 0 before this edge gets
    pc = spawn_pc and mask = 0001 (its in-flight bit is not touched by spawn). A spawn's pc and mask override a commit's on the
    same warp; this cannot happen in operation, but the block defines it.
""", clocked(i("start", 1, "control"), i("start_pc", W, "addr"), i("fire", 1, "valid"), i("fwid", 2, "addr"),
             i("commit", 1, "control"), i("cwid", 2, "addr"), i("c_pc", W, "addr"), i("c_tmask", 4, "control"),
             i("spawn_mask", 4, "control"), i("spawn_pc", W, "addr"),
             o("sel_pc", W, "addr"), o("sel_tmask", 4, "control"), o("active", 4, "control"), o("inflight", 4, "control"),
             o("busy", 1, "control")), reset_style="sync", latency=1)

PIPE_CTRL = block("b_pipe_ctrl", "pipe_ctrl", """
    Pipeline control, combinational. The X stage is busy while it holds a division whose result is not ready or a memory
    access the load-store unit has not finished: x_busy = dx_valid & ((unit is DIV & div_ready is 0) | (unit is LSU &
    lsu_ready is 0)), with unit read through its encoding table. stall = x_busy (the S, D and X stages hold their
    instructions). advance = dx_valid & !x_busy: the instruction in X completes at the next rising edge. sched_en = running &
    !x_busy. fetch_idx = bits 10:2 of sf_pc when x_busy is 1, otherwise bits 10:2 of sel_pc: the instruction-memory word to
    read, so that a held D stage keeps seeing its own instruction.
""", [i("running", 1, "control"), i("dx_valid", 1, "valid"), i("unit", 3, "control", "unit"), i("div_ready", 1, "control"),
      i("lsu_ready", 1, "control"), i("sel_pc", W, "addr"), i("sf_pc", W, "addr"),
      o("stall", 1, "control"), o("advance", 1, "control"), o("sched_en", 1, "control"), o("fetch_idx", 9, "addr")])

IMEM = block("b_imem", "imem", "Instruction memory, 2 KB: 512 words of 32 bits.", [
    port("p_clk", "clk", "in", 1, "clock"), i("raddr", 9, "addr"), o("rdata", W, "data"),
    i("we", 1, "control"), i("waddr", 9, "addr"), i("wdata", W, "data"),
], latency=1, storage={
    # read one clock edge after the address (as an SRAM macro), written by the host before a kernel starts
    "kind": "memory", "depth": 512, "readStyle": "sync", "sameCycle": "old", "initial": "unknown",
    "resetClears": False, "zeroReg": False,
    "ports": {"we": "p_we", "wdata": "p_wdata", "rdata": "p_rdata", "waddr": "p_waddr", "raddr": "p_raddr"},
})

# --------------------------------------------------------------------------- #
# D stage
# --------------------------------------------------------------------------- #

DECODE = block("b_decode", "decode", """
    Instruction decoder, combinational, for RV32IM with CSR reads and the GPU's SIMT (custom-0, opcode 0x0B) and tensor
    (custom-1, opcode 0x2B) instructions. Fields copied from inst every time: rs1 = bits 19:15, rs2 = bits 24:20,
    rd = bits 11:7, csr_addr = bits 31:20, br_op = mem_size = simt_op = funct3 (bits 14:12), md_op = funct3 bits 1:0,
    tensor_op = funct3 bits 1:0, simt_mode = funct7 (bits 31:25) bits 1:0.
    Every other output has a default unless the instruction's class below sets it: unit NONE, alu_op ADD, a_sel 0, b_sel 0,
    immsel NO_IMMEDIATE, wb_src ALU, regwrite 0, ctrl NONE, mem_store 0, illegal 0. The classes (op = bits 6:0, f3 = funct3,
    f7 = funct7):
    LUI (0x37): unit ALU, alu_op PASS_B, b_sel 1, immsel IMM_U, regwrite 1.
    AUIPC (0x17): unit ALU, alu_op ADD, a_sel 1, b_sel 1, immsel IMM_U, regwrite 1.
    JAL (0x6F): unit ALU, a_sel 1, b_sel 1, immsel IMM_J, wb_src LINK, regwrite 1, ctrl JAL.
    JALR (0x67 with f3 0): unit ALU, b_sel 1, immsel IMM_I, wb_src LINK, regwrite 1, ctrl JALR.
    Branch (0x63, f3 not 2 or 3): unit ALU, immsel IMM_B, ctrl BRANCH.
    Load (0x03, f3 0, 1, 2, 4 or 5): unit LSU, b_sel 1, immsel IMM_I, wb_src LOAD, regwrite 1.
    Store (0x23, f3 0, 1 or 2): unit LSU, b_sel 1, immsel IMM_S, mem_store 1.
    OP-IMM (0x13): b_sel 1, immsel IMM_I, regwrite 1, unit ALU, alu_op by f3: 0 ADD, 2 SLT, 3 SLTU, 4 XOR, 6 OR, 7 AND,
    1 SLL (only with f7 0), 5 SRL (f7 0) or SRA (f7 0x20); any other f3/f7 is illegal.
    OP (0x33): regwrite 1; f7 0: unit ALU, alu_op by f3: 0 ADD, 1 SLL, 2 SLT, 3 SLTU, 4 XOR, 5 SRL, 6 OR, 7 AND; f7 0x20 with
    f3 0: SUB, with f3 5: SRA (unit ALU); f7 1: unit MUL with wb_src MUL when f3 < 4, unit DIV with wb_src DIV otherwise;
    anything else is illegal.
    FENCE (0x0F, any f3): the defaults (nothing happens).
    SYSTEM (0x73): f3 2, 3, 6 or 7 with rs1 = 0 is a CSR read: unit CSR, wb_src CSR, regwrite 1; anything else (a CSR write,
    ecall, ebreak, mret) is illegal.
    SIMT (0x0B): legal when f3 <= 4 with f7 = 0, or f3 = 5 with f7 <= 2, or f3 = 6 with f7 <= 3: unit SIMT, wb_src SIMT,
    regwrite 1 for f3 5 and 6 (vote, shuffle), else 0; otherwise illegal.
    Tensor (0x2B with f7 0 and f3 <= 3): legal when f3 0 has rd = 0, f3 1 always, f3 2 has rd = 0, f3 3 has rd, rs1 and rs2
    all 0: unit TENSOR, wb_src TENSOR, regwrite 1 for f3 1, else 0; otherwise illegal.
    Any other instruction is illegal. An illegal instruction has every default except illegal = 1.
""", [i("inst", W, "data"),
      o("rs1", 5, "addr"), o("rs2", 5, "addr"), o("rd", 5, "addr"), o("immsel", 3, "control", "immsel"),
      o("unit", 3, "control", "unit"), o("alu_op", 4, "control", "alu_op"), o("a_sel", 1, "control"), o("b_sel", 1, "control"),
      o("wb_src", 3, "control", "wb_src"), o("regwrite", 1, "control"), o("ctrl", 2, "control", "ctrl"),
      o("br_op", 3, "control", "br_op"), o("mem_store", 1, "control"), o("mem_size", 3, "control"), o("md_op", 2, "control"),
      o("simt_op", 3, "control", "simt_op"), o("simt_mode", 2, "control"), o("tensor_op", 2, "control", "tensor_op"),
      o("csr_addr", 12, "addr"), o("illegal", 1, "control")])

IMM_GEN = next(b for b in sc.BLOCKS if b["name"] == "imm_gen")     # the RV32I demo's block, unchanged

def lane_regfile(k):
    return block(f"b_regfile{k}", f"regfile{k}", f"""
        Lane {k}'s register file, for all four warps: 128 words of 32 bits (word = warp x 32 + register). Lane {k} of every
        warp's registers lives here, so the four lanes read and write their registers in parallel.
    """, [port("p_clk", "clk", "in", 1, "clock"), i("raddr", 7, "addr"), o("rdata", W, "data"), i("raddr2", 7, "addr"),
          o("rdata2", W, "data"), i("we", 1, "control"), i("waddr", 7, "addr"), i("wdata", W, "data")],
        latency=1, storage={
            # two reads at once (no clock), one write per clock edge; x0 is handled by `operand`, since every warp has one
            "kind": "regfile", "depth": 128, "readStyle": "async", "sameCycle": "old", "initial": "unknown",
            "resetClears": False, "zeroReg": False,
            "ports": {"we": "p_we", "wdata": "p_wdata", "rdata": "p_rdata", "waddr": "p_waddr", "raddr": "p_raddr",
                      "raddr2": "p_raddr2", "rdata2": "p_rdata2"},
        })


REGFILES = [lane_regfile(k) for k in range(4)]

OPERAND = block("b_operand", "operand", """
    Operand stage, combinational. raddr1 = wid * 32 + rs1 and raddr2 = wid * 32 + rs2 (7 bits: the word of that warp's register
    in each lane's register file). a gathers the four lanes' first reads, lane k (bits 32k+31..32k) = rdata1_k, and is 0 when
    rs1 is 0; b gathers rdata2_k the same way and is 0 when rs2 is 0 (register x0 reads 0 in every warp, whatever the
    register files hold).
""", [i("wid", 2, "addr"), i("rs1", 5, "addr"), i("rs2", 5, "addr"),
      *[i(f"rdata1_{k}", W, "data") for k in range(4)], *[i(f"rdata2_{k}", W, "data") for k in range(4)],
      o("raddr1", 7, "addr"), o("raddr2", 7, "addr"), o("a", V, "data"), o("b", V, "data")])

# --------------------------------------------------------------------------- #
# X stage
# --------------------------------------------------------------------------- #

VALU = block("b_valu", "valu", f"""
    Four-lane arithmetic unit, combinational. {LANES} For each lane i: x = pc when a_sel is 1, else lane i of a; z = imm when
    b_sel is 1, else lane i of b; lane i of y = alu_op applied to x and z (its encoding table; shifts use z bits 4:0; results
    are 32 bits). Bit i of taken compares lane i of a with lane i of b (never x and z) by br_op's encoding table.
""", [i("a", V, "data"), i("b", V, "data"), i("imm", W, "data"), i("pc", W, "addr"), i("a_sel", 1, "control"),
      i("b_sel", 1, "control"), i("alu_op", 4, "control", "alu_op"), i("br_op", 3, "control", "br_op"),
      o("y", V, "data"), o("taken", 4, "control")])

VMUL = block("b_vmul", "vmul", f"""
    Four-lane multiplier, combinational. {LANES} For each lane, with x = lane i of a and z = lane i of b: md_op 0 MUL, the
    low 32 bits of x * z; 1 MULH, the high 32 bits of the 64-bit product with both signed; 2 MULHSU, x signed and z unsigned;
    3 MULHU, both unsigned.
""", [i("a", V, "data"), i("b", V, "data"), i("md_op", 2, "control"), o("y", V, "data")])

VDIV = block("b_vdiv", "vdiv", f"""
    Four-lane iterative divider. {LANES} start = valid & (unit is DIV). It has three states, IDLE, BUSY and DONE, and a 5-bit
    count. ready is 1 exactly in DONE; y is the four results in DONE and 0 otherwise. On each rising edge: when rst or clear is
    1, IDLE. In IDLE with start: take a, b and md_op, count = 0, go to BUSY. In BUSY: when count is 31 go to DONE, otherwise
    count + 1 (BUSY lasts exactly 32 cycles, one quotient bit per cycle). In DONE with advance: IDLE. The result for each lane,
    with x = lane i of a and z = lane i of b (RISC-V M): md_op 0 DIV, signed, rounding toward zero, x / 0 = all ones and
    -2^31 / -1 = -2^31; 1 DIVU, unsigned, x / 0 = all ones; 2 REM, signed with the sign of x, x rem 0 = x and -2^31 rem -1 = 0;
    3 REMU, unsigned, x remu 0 = x.
""", clocked(i("clear", 1, "control"), i("valid", 1, "valid"), i("unit", 3, "control", "unit"), i("md_op", 2, "control"),
             i("a", V, "data"), i("b", V, "data"), i("advance", 1, "control"), o("ready", 1, "control"), o("y", V, "data")),
    reset_style="sync", latency=33)

BRANCH_UNIT = block("b_branch_unit", "branch_unit", f"""
    Branch unit, combinational. {LANES} The warp follows its lowest-numbered active lane l (bit l of tmask). When tmask is 0 there
    is no active lane and next_pc = pc + 4, diverged = 0, whatever ctrl says. link = pc + 4. next_pc by ctrl's encoding table: NONE pc + 4; BRANCH pc + imm when taken bit l is 1, else pc + 4;
    JAL pc + imm; JALR (lane l of a + imm) with bit 0 cleared. diverged = 1 when the active lanes do not all agree: for BRANCH, when their taken bits differ; for JALR, when their targets
    (lane value of a + imm) differ; it is 0 for JAL and NONE and when no lane is active (a branch on lane-dependent data, which
    the instruction set forbids); it changes nothing else.
""", [i("ctrl", 2, "control", "ctrl"), i("taken", 4, "control"), i("tmask", 4, "control"), i("pc", W, "addr"),
      i("imm", W, "data"), i("a", V, "data"), o("next_pc", W, "addr"), o("link", W, "data"), o("diverged", 1, "control")])

VOTE_SHFL = block("b_vote_shfl", "vote_shfl", f"""
    Vote and shuffle unit, combinational. {LANES} When simt_op is VOTE: ballot = the 4-bit mask of lanes active in tmask whose 32-bit lane of a
    is not 0; each of the four 32-bit lanes of y (bits 32l+31..32l) gets the same 32-bit value, the following zero-extended to
    32 bits, by simt_mode: 0 any (1 when ballot is not 0, else 0), 1 all (1 when ballot equals tmask),
    2 ballot itself, 3 zero. When simt_op is SHFL: lane l of y = lane s of a, whatever the mask, where k = lane l of b
    (unsigned) and by simt_mode: 0 s = k mod 4; 1 s = (l xor k) mod 4; 2 s = l - k, or l when k > l; 3 s = l + k, or l
    when l + k >= 4. Here k is the whole 32-bit unsigned value: for modes 2 and 3 any k of 4 or more (any of bits 31:2 set) gives
    s = l. Any other simt_op: y = 0.
""", [i("simt_op", 3, "control", "simt_op"), i("simt_mode", 2, "control"), i("tmask", 4, "control"), i("a", V, "data"),
      i("b", V, "data"), o("y", V, "data")])

SIMT_CTRL = block("b_simt_ctrl", "simt_ctrl", f"""
    SIMT control, combinational: the warp's next pc and thread mask at commit, and the requests to the divergence stack, the
    warp table and the barriers. {LANES} fa and fb are lane l of a and of b, for the lowest-numbered active lane l, chosen with
    four select wires: sel0 = tmask[0] OR (tmask == 4'b0000); sel1 = !tmask[0] AND tmask[1]; sel2 = !tmask[0] AND !tmask[1]
    AND tmask[2]; sel3 = !tmask[0] AND !tmask[1] AND !tmask[2] AND tmask[3]. Note that when tmask is 4'b0000 sel0 is 1 and the
    others are 0, so fa and fb are lane 0 (not lane 3, not 0): the same lane 0 that is used when lane 0 is active. p4 = pc + 4. When valid is 0 or unit is not SIMT: c_pc = br_next_pc, c_tmask = tmask and every other output
    is 0. Otherwise c_pc = p4 and c_tmask = tmask unless set below, and by simt_op:
    TMC: c_tmask = fa bits 3:0; clear = 1 when that is 0 (the warp ends and its stack empties).
    WSPAWN: spawn_mask bit w (w = 1, 2, 3) = 1 when w < fa (unsigned), bit 0 = 0; spawn_pc = fb.
    SPLIT: pred = the active lanes whose a lane is not 0, T = tmask & pred, F = tmask & ~pred. When depth + n > 8 (depth is a 4-bit input that never exceeds 8 in operation, but the sum is compared without wrapping), where n is
    2 when both T and F are non-empty and 1 otherwise: err = 1 and nothing is pushed. Otherwise push = n with e0 = (mask
    tmask, pc 0, fall 1). When n is 2 (both T and F non-empty): e1 = (mask F, pc p4, fall 0) and c_tmask = T. When n is 1
    (every active lane agrees, so T or F is empty): there is no e1 and c_tmask = tmask, unchanged, even if the predicate is false in
    every lane (T is then empty, but the mask does not become 0).
    JOIN: when depth is 0, err = 1; otherwise pop = 1, c_tmask = top_mask, and c_pc = p4 when top_fall is 1, else top_pc.
    BAR: bar_arrive = 1, bar_id = fa bits 1:0, bar_count = fb when fb < 7, else 7; err = 1 when fa > 3.
    VOTE, SHFL and the code 111: nothing more.
    push, pop, clear, spawn_mask and bar_arrive are forced to 0 whenever advance is 0, so they act only at the edge where the
    instruction completes. Only those five depend on advance. All the other outputs (c_pc, c_tmask, e0_*, e1_*, spawn_pc,
    bar_id, bar_count, err) are computed as above whatever advance is, including when advance is 0: for example a BAR with
    fa > 3 has err = 1 and bar_count set, and a WSPAWN has spawn_pc = fb, even when advance is 0. Every unset field of e0 and e1 is 0.
""", [i("valid", 1, "valid"), i("unit", 3, "control", "unit"), i("advance", 1, "control"), i("simt_op", 3, "control", "simt_op"),
      i("tmask", 4, "control"), i("pc", W, "addr"), i("br_next_pc", W, "addr"), i("a", V, "data"), i("b", V, "data"),
      i("top_mask", 4, "control"), i("top_pc", W, "addr"), i("top_fall", 1, "control"), i("depth", 4, "data"),
      o("c_pc", W, "addr"), o("c_tmask", 4, "control"), o("push", 2, "control"),
      o("e0_mask", 4, "control"), o("e0_pc", W, "addr"), o("e0_fall", 1, "control"),
      o("e1_mask", 4, "control"), o("e1_pc", W, "addr"), o("e1_fall", 1, "control"),
      o("pop", 1, "control"), o("clear", 1, "control"), o("spawn_mask", 4, "control"), o("spawn_pc", W, "addr"),
      o("bar_arrive", 1, "control"), o("bar_id", 2, "addr"), o("bar_count", 3, "data"), o("err", 1, "control")])

IPDOM = block("b_ipdom", "ipdom", """
    Divergence stacks: one stack of up to 8 entries for each of the 4 warps; an entry is a 4-bit mask, a 32-bit pc and a fall
    bit. Outputs, combinational from the state and wid: depth (0 to 8) of warp wid's stack, and its top entry (the one pushed
    last) as top_mask, top_pc and top_fall, all 0 when the stack is empty. On each rising edge: when rst or clear_all is 1,
    every stack becomes empty. Otherwise, when en is 1, on warp wid's stack, the first of these that applies: clear empties it;
    pop removes the top entry (nothing when empty); push 1 adds e0; push 2 adds e0 and then e1 (so e1 is on top). A push that
    would take the stack past 8 entries changes nothing.
""", clocked(i("clear_all", 1, "control"), i("wid", 2, "addr"), i("en", 1, "control"), i("push", 2, "control"),
             i("e0_mask", 4, "control"), i("e0_pc", W, "addr"), i("e0_fall", 1, "control"),
             i("e1_mask", 4, "control"), i("e1_pc", W, "addr"), i("e1_fall", 1, "control"),
             i("pop", 1, "control"), i("clear", 1, "control"),
             o("depth", 4, "data"), o("top_mask", 4, "control"), o("top_pc", W, "addr"), o("top_fall", 1, "control")),
    reset_style="sync", latency=1)

BARRIER = block("b_barrier_unit", "barrier_unit", """
    Barriers: four barriers, each with a 4-bit arrived mask (bit w: warp w has arrived), and a 4-bit waiting register (bit w:
    warp w waits), which is the output. On each rising edge: when rst or clear_all is 1, every arrived mask and waiting bit
    becomes 0. Otherwise when en is 1: let m = arrived[bar_id] | (1 << wid). When the number of 1 bits in m is at least
    bar_count, the barrier releases: arrived[bar_id] becomes 0 and every warp in m stops waiting (waiting &= ~m). Otherwise
    arrived[bar_id] becomes m and warp wid waits (its waiting bit becomes 1).
""", clocked(i("clear_all", 1, "control"), i("en", 1, "control"), i("wid", 2, "addr"), i("bar_id", 2, "addr"),
             i("bar_count", 3, "data"), o("waiting", 4, "control")), reset_style="sync", latency=1)

TENSOR = block("b_tensor_unit", "tensor_unit", f"""
    Tensor unit. {LANES} For each of the 4 warps, a 4 x 4 accumulator ACC of 32-bit values (lane i owns row i).
    is_t = valid & (unit is TENSOR). Outputs, combinational: err = is_t & (tmask is not 1111); lane i of ld_y =
    ACC[wid][i][c] where c = lane i of a, bits 1:0 (whatever the operation). On each rising edge: when rst or clear_all is 1,
    every accumulator becomes 0. Otherwise when advance & is_t & !err, by tensor_op: MMA_I8: ACC[wid][i][j] += the sum over
    k = 0..3 of A[i][k] * B[k][j] (32-bit wrapping), where A[i][k] is byte k (bits 8k+7..8k) of lane i of a and B[k][j] is
    byte k of lane j of b, both signed 8-bit; this is one 4 x 4 x 4 multiply-accumulate per instruction (64 products).
    MMA_LD: nothing changes. MMA_ST: ACC[wid][i][c] = lane i of a for every lane i, where c = lane i of b, bits 1:0.
    MMA_ZERO: every entry of ACC[wid] becomes 0.
    Exact indexing, to avoid transposing: A[i][k] = byte k of lane i of a = a[32*i + 8*k + 7 : 32*i + 8*k] (row i of A comes
    from lane i of a); B[k][j] = byte k of lane j of b = b[32*j + 8*k + 7 : 32*j + 8*k] (column j of B comes from lane j of b:
    the lane picks the column j and the byte picks k, never the other way round). Each product A[i][k] * B[k][j] is a SIGNED
    8-bit by signed 8-bit product (a signed 16-bit value), sign-extended to 32 bits before it is added; the four products
    and the old ACC[wid][i][j] are added as 32-bit two's-complement values (wrapping). ACC entry (wid, i, j) is element
    16*wid + 4*i + j of the flat array. In MMA_LD / ld_y and MMA_ST the column c of lane i is a[32*i + 1 : 32*i] and
    b[32*i + 1 : 32*i] respectively.
    Worked example (after MMA_ZERO, one MMA_I8, wid 0, tmask 1111): a = {{lane3: 0, lane2: 32'h000000FF, lane1: 32'h00000002,
    lane0: 32'h0302FF01}} (lane 0 holds A[0][0..3] = 1, -1, 2, 3); b = {{lane3: 0, lane2: 0, lane1: 32'h01010101, lane0:
    32'h07FA0504}} (lane 0 holds B[0..3][0] = 4, 5, -6, 7; lane 1 holds B[0..3][1] = 1, 1, 1, 1). Then ACC[0][0][0] = 1*4 +
    (-1)*5 + 2*(-6) + 3*7 = 8; ACC[0][0][1] = 1 - 1 + 2 + 3 = 5; ACC[0][1][0] = 2*4 = 8; ACC[0][1][1] = 2*1 = 2;
    ACC[0][2][0] = -1*4 = -4 = 32'hFFFFFFFC; ACC[0][2][1] = -1 = 32'hFFFFFFFF; every other entry is 0.
    Implementation note: hold the 64 accumulator entries as a flat 1-D array or as
    separate registers (no multi-dimensional arrays), so that every simulator reads them correctly.
""", clocked(i("clear_all", 1, "control"), i("valid", 1, "valid"), i("unit", 3, "control", "unit"), i("advance", 1, "control"),
             i("tensor_op", 2, "control", "tensor_op"), i("wid", 2, "addr"), i("tmask", 4, "control"), i("a", V, "data"),
             i("b", V, "data"), o("ld_y", V, "data"), o("err", 1, "control")), reset_style="sync", latency=1)

CSR = block("b_csr", "csr", f"""
    CSR read unit, combinational. {LANES} Lane l of y = the value of CSR csr_addr for that lane: 0xCC0 tid = l; 0xCC1 wid;
    0xCC2 cid = 0; 0xCC3 tmask; 0xCC4 gtid = wid * 4 + l; 0xCC5 karg; 0xFC0 nt = 4; 0xFC1 nw = 4; 0xFC2 nc = 1; 0xC00 cycle
    and 0xC02 instret = cycle bits 31:0; 0xC80 cycleh and 0xC82 instreth = cycle bits 47:32 (zero-extended; the counter is 48 bits). Any other address: y = 0, and
    err = 1 when valid is 1 and unit is CSR (err is 0 in every other case).
""", [i("csr_addr", 12, "addr"), i("valid", 1, "valid"), i("unit", 3, "control", "unit"), i("wid", 2, "addr"),
      i("tmask", 4, "control"), i("karg", W, "data"), i("cycle", 48, "data"), o("y", V, "data"), o("err", 1, "control")])

CYCLE_CTR = block("b_cycle_ctr", "cycle_ctr", "Cycle counter, 48 bits: counts the clock cycles while the core is running (wraps after 2^48).",
                  clocked(i("enable", 1, "control"), o("count", 48, "data")), reset_style="sync", latency=1)
CYCLE_CTR["counter"] = {"direction": "up", "step": 1, "limit": "wrap", "resetValue": 0,
                        "ports": {"count": "p_count", "enable": "p_enable"}}

LSU = block("b_lsu", "lsu", f"""
    Load-store unit for global memory (4 banks of 512 words) and shared memory (4 banks of 256 words); bank k holds the words
    whose address bits 3:2 are k. {LANES} Packed bank ports: bank k uses bit k of g_en, g_we, s_en and s_we; bits 9k+8..9k of
    g_addr; bits 8k+7..8k of s_addr; bits 32k+31..32k of g_wdata, s_wdata, g_rdata and s_rdata; bits 4k+3..4k of g_be and
    s_be. A bank's rdata shows the word it was addressed with in the previous cycle.
    act = valid & (unit is LSU). Lane i's address A = lane i of a + imm (32 bits); n bytes = 1 for mem_size 0 and 4, 2 for 1
    and 5, 4 otherwise. A lane is in global memory when 0x1000_0000 <= A < 0x1000_2000 (word index (A - 0x1000_0000) >> 4)
    and in shared memory when 0x2000_0000 <= A < 0x2000_1000 (word index (A - 0x2000_0000) >> 4); its bank is A bits 3:2 and
    its byte offset A bits 1:0. err = act & !started & (some lane active in tmask has A mod n != 0 or is in neither memory).
    Registers: started (1 bit), pend (4: lanes still to access), got (4: lanes whose loaded word arrives this cycle), cap (128).
    P = tmask when started is 0, else pend. Requests, only when act & !err: for each memory and each bank, the
    lowest-numbered lane in P mapped to it is chosen and drives that bank: en 1, we = mem_store, addr = its word index,
    wdata = (lane i of b) << (8 * offset) truncated to 32 bits, be = ((1 << n) - 1) << offset (4 bits). Every other bank
    field is 0. Loaded data: cur = cap with each lane in got replaced by its n bytes at its offset in its bank's rdata,
    sign-extended for mem_size 0 and 1 and zero-extended otherwise; y = cur.
    ready = act & (err | (mem_store & every lane of P is chosen in this cycle) | (!mem_store & started & P == 0)).
    On each rising edge: when rst is 1, started = 0, pend = 0, got = 0 and cap = 0; when clear or advance is 1 (and rst is 0)
    started = 0, pend = 0, got = 0 and cap keeps its value. Otherwise when act & !err:
    started = 1, pend = P without the chosen lanes, got = the chosen lanes for a load (0 for a store), cap = cur.
    So an access with one lane per bank takes one cycle to store and two to load; each extra lane in one bank costs a cycle,
    and lanes in the same bank are served in lane order (for a store to one address, the highest lane's value stays).
""", clocked(i("clear", 1, "control"), i("valid", 1, "valid"), i("unit", 3, "control", "unit"), i("mem_store", 1, "control"),
             i("mem_size", 3, "control"), i("tmask", 4, "control"), i("a", V, "data"), i("b", V, "data"), i("imm", W, "data"),
             i("advance", 1, "control"), i("g_rdata", V, "data"), i("s_rdata", V, "data"),
             o("g_en", 4, "control"), o("g_we", 4, "control"), o("g_addr", 36, "addr"), o("g_wdata", V, "data"),
             o("g_be", 16, "control"), o("s_en", 4, "control"), o("s_we", 4, "control"), o("s_addr", 32, "addr"),
             o("s_wdata", V, "data"), o("s_be", 16, "control"),
             o("ready", 1, "control"), o("y", V, "data"), o("err", 1, "control")), reset_style="sync", latency=1)

BANK_MUX = block("b_bank_mux", "bank_mux", """
    Memory port switch, combinational. While running is 1 the load-store unit owns the eight banks: global bank k gets
    we = g_en bit k & g_we bit k, and addr, wdata and be from field k of the packed g_addr, g_wdata and g_be (bank k: bits
    9k+8..9k of g_addr, 32k+31..32k of g_wdata, 4k+3..4k of g_be); shared bank k likewise from the s_ ports (bits 8k+7..8k of
    s_addr). The instruction memory's write port is off: imem_we is 0 (and imem_waddr and imem_wdata are don't-care whenever imem_we is 0).
    The host's ranges, as bit slices of host_addr (use exactly these): instruction memory when host_addr bits 31:11 are all 0
    (21 bits, 0); global memory when bits 31:13 equal 19'h08000 (19 bits); shared memory when bits 31:12 equal 20'h20000 (20 bits).
    While running is 0 the host owns them, one 32-bit word at a time: when host_addr is in 0x0000_0000..0x0000_07FF,
    imem_we = host_en & host_we, imem_waddr = host_addr bits 10:2, imem_wdata = host_wdata. When it is in
    0x1000_0000..0x1000_1FFF, global bank k = host_addr bits 3:2 gets addr = (host_addr - 0x1000_0000) >> 4,
    we = host_en & host_we, wdata = host_wdata and be = 1111. When it is in 0x2000_0000..0x2000_0FFF, shared bank k =
    host_addr bits 3:2 likewise with addr = (host_addr - 0x2000_0000) >> 4. In host mode every bank the host is not
    addressing has we = 0, and its addr, wdata and be are don't-care. In load-store mode every port is as the packed ports give it.
    Always: g_rdata packs the four global banks' rdata (bank k in bits 32k+31..32k), and s_rdata the four shared banks'.
""", [i("running", 1, "control"), i("g_en", 4, "control"), i("g_we", 4, "control"), i("g_addr", 36, "addr"),
      i("g_wdata", V, "data"), i("g_be", 16, "control"), i("s_en", 4, "control"), i("s_we", 4, "control"),
      i("s_addr", 32, "addr"), i("s_wdata", V, "data"), i("s_be", 16, "control"),
      i("host_en", 1, "valid"), i("host_we", 1, "control"), i("host_addr", W, "addr"), i("host_wdata", W, "data"),
      *[i(f"gb{k}_rdata", W, "data") for k in range(4)], *[i(f"sb{k}_rdata", W, "data") for k in range(4)],
      *[p for k in range(4) for p in (o(f"gb{k}_we", 1, "control"), o(f"gb{k}_addr", 9, "addr"), o(f"gb{k}_wdata", W, "data"),
                                      o(f"gb{k}_be", 4, "control"))],
      *[p for k in range(4) for p in (o(f"sb{k}_we", 1, "control"), o(f"sb{k}_addr", 8, "addr"), o(f"sb{k}_wdata", W, "data"),
                                      o(f"sb{k}_be", 4, "control"))],
      o("imem_we", 1, "control"), o("imem_waddr", 9, "addr"), o("imem_wdata", W, "data"),
      o("g_rdata", V, "data"), o("s_rdata", V, "data")])


def bank(name, depth, abits, what):
    return block(f"b_{name}", name, f"{what}: {depth} words of 32 bits, with a byte enable per byte.", [
        port("p_clk", "clk", "in", 1, "clock"), i("addr", abits, "addr"), i("we", 1, "control"), i("wdata", W, "data"),
        i("be", 4, "control"), o("rdata", W, "data"),
    ], latency=1, storage={
        # one address for reading and writing; read one edge after the address (an SRAM macro); contents unknown at power-up
        "kind": "memory", "depth": depth, "readStyle": "sync", "sameCycle": "old", "initial": "unknown",
        "resetClears": False, "zeroReg": False,
        "ports": {"we": "p_we", "wdata": "p_wdata", "rdata": "p_rdata", "waddr": "p_addr", "raddr": "p_addr", "be": "p_be"},
    })


GBANKS = [bank(f"gbank{k}", 512, 9, f"Global memory bank {k} (the words whose address bits 3:2 are {k})") for k in range(4)]
SBANKS = [bank(f"sbank{k}", 256, 8, f"Shared memory bank {k} (the words whose address bits 3:2 are {k})") for k in range(4)]

WB_MUX = block("b_wb_mux", "wb_mux", f"""
    Write-back selector, combinational. {LANES} Let w = advance & regwrite & (rd != 0) and r = the source wb_src's encoding
    table selects: alu_y, mul_y, div_y, load_y, simt_y, tensor_y, csr_y, or link in every lane. For each lane k: we_k = w &
    tmask bit k (only active lanes write) and wdata_k = lane k of r. waddr = wid * 32 + rd.
""", [i("advance", 1, "control"), i("regwrite", 1, "control"), i("rd", 5, "addr"), i("wid", 2, "addr"), i("tmask", 4, "control"),
      i("wb_src", 3, "control", "wb_src"), i("alu_y", V, "data"), i("mul_y", V, "data"), i("div_y", V, "data"),
      i("load_y", V, "data"), i("simt_y", V, "data"), i("tensor_y", V, "data"), i("csr_y", V, "data"), i("link", W, "data"),
      *[o(f"we{k}", 1, "control") for k in range(4)], o("waddr", 7, "addr"), *[o(f"wdata{k}", W, "data") for k in range(4)]])

HOST_IF = block("b_host_if", "host_if", """
    Host interface. The host bus: host_en, host_we, host_addr, host_wdata in; host_rdata and host_rvalid out; a read's data
    comes in the cycle after the request, with host_rvalid = 1. Registers: running, done, error (1 bit each), start_pc,
    karg, err_pc (32 bits), err_info (10 bits), rvalid (1) and raddr (32). Control addresses: 0x3000_0000 CTRL (write bit 0 =
    1 to start), 0x3000_0004 START_PC, 0x3000_0008 KARG, 0x3000_000C STATUS (bit 0 running, bit 1 done, bit 2 error),
    0x3000_0010 ERR_PC, 0x3000_0014 ERR_INFO. ERR_INFO is 10 bits wide, laid out as: bits 3:0 the cause (a number 0 to 5),
    bits 7:4 always 0, bits 9:8 the warp x_wid (2 bits). As a concatenation: err_info <= {x_wid, 4'b0000, cause[3:0]}.
    Example: cause 3 in warp 2 gives err_info = 10'b10_0000_0011 (0x203); cause 1 in warp 0 gives 10'b00_0000_0001 (0x001).
    Outputs: running, done, error, start_pc and karg show their registers; host_rvalid shows rvalid; start (combinational) =
    host_en & host_we & (host_addr == 0x3000_0000) & host_wdata bit 0 & !running. The cause of an error is the first of
    err_illegal (1), err_mem (2), err_simt (3), err_tensor (4), err_csr (5) that is 1, or 0 when none is.
    On each rising edge: when rst is 1 every register becomes 0. Otherwise: a host write (host_en & host_we) while running is
    0 to START_PC or KARG stores host_wdata there. Then the first that applies: start: running 1, done 0, error 0; running &
    advance & a cause: running 0, error 1, err_pc = x_pc, err_info = {x_wid, 4'b0000, cause[3:0]} (the cause in the low 4 bits, the warp in bits 9:8); running & !busy: running 0,
    done 1. And always rvalid = host_en & !host_we and raddr = host_addr.
    host_rdata, combinational from raddr: when raddr is in 0x1000_0000..0x1000_1FFF, word (raddr bits 3:2) of g_rdata
    (bits 32k+31..32k for word k); in 0x2000_0000..0x2000_0FFF the same of s_rdata; at a control address its register's
    present value (STATUS as described, CTRL reads 0); anywhere else 0.
""", clocked(i("host_en", 1, "valid"), i("host_we", 1, "control"), i("host_addr", W, "addr"), i("host_wdata", W, "data"),
             i("busy", 1, "control"), i("advance", 1, "control"), i("x_pc", W, "addr"), i("x_wid", 2, "addr"),
             i("err_illegal", 1, "control"), i("err_mem", 1, "control"), i("err_simt", 1, "control"),
             i("err_tensor", 1, "control"), i("err_csr", 1, "control"), i("g_rdata", V, "data"), i("s_rdata", V, "data"),
             o("host_rdata", W, "data"), o("host_rvalid", 1, "valid"), o("running", 1, "control"), o("start", 1, "control"),
             o("start_pc", W, "addr"), o("karg", W, "data"), o("done", 1, "control"), o("error", 1, "control")),
    reset_style="sync", latency=1)

BLOCKS = [WARP_SCHED, WARP_TABLE, PIPE_CTRL, IMEM, SF_REG, DECODE, IMM_GEN, *REGFILES, OPERAND, DX_REG, VALU, VMUL, VDIV,
          BRANCH_UNIT, VOTE_SHFL, SIMT_CTRL, IPDOM, BARRIER, TENSOR, CSR, CYCLE_CTR, LSU, BANK_MUX, *GBANKS, *SBANKS,
          WB_MUX, HOST_IF]

# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #

TOP = None
TOP_PORTS = [
    {"blockId": None, **port("t_clk", "clk", "in", 1, "clock")},
    {"blockId": None, **port("t_rst", "rst", "in", 1, "reset")},
    {"blockId": None, **port("t_host_en", "host_en", "in", 1, "valid")},
    {"blockId": None, **port("t_host_we", "host_we", "in", 1, "control")},
    {"blockId": None, **port("t_host_addr", "host_addr", "in", W, "addr")},
    {"blockId": None, **port("t_host_wdata", "host_wdata", "in", W, "data")},
    {"blockId": None, **port("t_host_rdata", "host_rdata", "out", W, "data")},
    {"blockId": None, **port("t_host_rvalid", "host_rvalid", "out", 1, "valid")},
    {"blockId": None, **port("t_running", "running", "out", 1, "control")},
    {"blockId": None, **port("t_done", "done", "out", 1, "control")},
    {"blockId": None, **port("t_error", "error", "out", 1, "control")},
    {"blockId": None, **port("t_diverged", "diverged", "out", 1, "control")},
]

b = lambda name: f"b_{name}"   # noqa: E731


def to(*pairs):
    """sinks: to('valu.a', 'vmul.a') -> [(block id, port id), ...]"""
    out = []
    for s in pairs:
        blk, prt = s.split(".")
        out.append((TOP, f"t_{prt}") if blk == "top" else (b(blk), f"p_{prt}"))
    return out


def frm(s):
    blk, prt = s.split(".")
    return (TOP, f"t_{prt}") if blk == "top" else (b(blk), f"p_{prt}")


CLOCKED = ["warp_sched", "warp_table", "sf_reg", "dx_reg", "vdiv", "ipdom", "barrier_unit", "tensor_unit", "cycle_ctr", "lsu",
           "host_if"]
MEMORIES = ["imem"] + [f"regfile{k}" for k in range(4)] + [f"gbank{k}" for k in range(4)] + [f"sbank{k}" for k in range(4)]
X_UNITS_VALID = ["vdiv", "simt_ctrl", "csr", "tensor_unit", "lsu"]

WIRES = [
    ("clock", 1, frm("top.clk"), to(*[f"{n}.clk" for n in CLOCKED + MEMORIES])),
    ("reset", 1, frm("top.rst"), to(*[f"{n}.rst" for n in CLOCKED])),
    ("host_en", 1, frm("top.host_en"), to("bank_mux.host_en", "host_if.host_en")),
    ("host_we", 1, frm("top.host_we"), to("bank_mux.host_we", "host_if.host_we")),
    ("host_addr", W, frm("top.host_addr"), to("bank_mux.host_addr", "host_if.host_addr")),
    ("host_wdata", W, frm("top.host_wdata"), to("bank_mux.host_wdata", "host_if.host_wdata")),
    ("host_rdata", W, frm("host_if.host_rdata"), to("top.host_rdata")),
    ("host_rvalid", 1, frm("host_if.host_rvalid"), to("top.host_rvalid")),
    ("running", 1, frm("host_if.running"), to("pipe_ctrl.running", "bank_mux.running", "cycle_ctr.enable", "top.running")),
    ("done", 1, frm("host_if.done"), to("top.done")),
    ("error", 1, frm("host_if.error"), to("top.error")),
    ("start", 1, frm("host_if.start"), to("warp_sched.start", "warp_table.start", "sf_reg.clear", "dx_reg.clear", "vdiv.clear",
                                          "ipdom.clear_all", "barrier_unit.clear_all", "tensor_unit.clear_all", "lsu.clear")),
    ("start_pc", W, frm("host_if.start_pc"), to("warp_table.start_pc")),
    ("karg", W, frm("host_if.karg"), to("csr.karg")),

    # S stage
    ("sched_en", 1, frm("pipe_ctrl.sched_en"), to("warp_sched.enable")),
    ("warp_active", 4, frm("warp_table.active"), to("warp_sched.active")),
    ("warp_inflight", 4, frm("warp_table.inflight"), to("warp_sched.inflight")),
    ("warp_waiting", 4, frm("barrier_unit.waiting"), to("warp_sched.waiting")),
    ("fire", 1, frm("warp_sched.fire"), to("warp_table.fire", "sf_reg.valid_in")),
    ("fwid", 2, frm("warp_sched.fwid"), to("warp_table.fwid", "sf_reg.wid_in")),
    ("sel_pc", W, frm("warp_table.sel_pc"), to("pipe_ctrl.sel_pc", "sf_reg.pc_in")),
    ("sel_tmask", 4, frm("warp_table.sel_tmask"), to("sf_reg.tmask_in")),
    ("busy", 1, frm("warp_table.busy"), to("host_if.busy")),
    ("fetch_idx", 9, frm("pipe_ctrl.fetch_idx"), to("imem.raddr")),
    ("stall", 1, frm("pipe_ctrl.stall"), to("sf_reg.hold", "dx_reg.hold")),

    # D stage
    ("d_valid", 1, frm("sf_reg.valid_out"), to("dx_reg.valid_in")),
    ("d_wid", 2, frm("sf_reg.wid_out"), to("operand.wid", "dx_reg.wid_in")),
    ("d_pc", W, frm("sf_reg.pc_out"), to("pipe_ctrl.sf_pc", "dx_reg.pc_in")),
    ("d_tmask", 4, frm("sf_reg.tmask_out"), to("dx_reg.tmask_in")),
    ("d_inst", W, frm("imem.rdata"), to("decode.inst", "imm_gen.inst")),
    ("d_rs1", 5, frm("decode.rs1"), to("operand.rs1")),
    ("d_rs2", 5, frm("decode.rs2"), to("operand.rs2")),
    ("d_immsel", 3, frm("decode.immsel"), to("imm_gen.immsel")),
    ("d_imm", W, frm("imm_gen.imm"), to("dx_reg.imm_in")),
    ("rf_raddr1", 7, frm("operand.raddr1"), to(*[f"regfile{k}.raddr" for k in range(4)])),
    ("rf_raddr2", 7, frm("operand.raddr2"), to(*[f"regfile{k}.raddr2" for k in range(4)])),
    *[(f"rf{k}_rdata1", W, frm(f"regfile{k}.rdata"), to(f"operand.rdata1_{k}")) for k in range(4)],
    *[(f"rf{k}_rdata2", W, frm(f"regfile{k}.rdata2"), to(f"operand.rdata2_{k}")) for k in range(4)],
    ("d_a", V, frm("operand.a"), to("dx_reg.a_in")),
    ("d_b", V, frm("operand.b"), to("dx_reg.b_in")),
    *[(f"d_{f}", w, frm(f"decode.{f}"), to(f"dx_reg.{f}_in"))
      for f, w, _, _ in DX_FIELDS if f not in ("valid", "wid", "pc", "tmask", "imm", "a", "b")],

    # X stage
    ("x_valid", 1, frm("dx_reg.valid_out"), to("pipe_ctrl.dx_valid", *[f"{n}.valid" for n in X_UNITS_VALID])),
    ("x_unit", 3, frm("dx_reg.unit_out"), to("pipe_ctrl.unit", *[f"{n}.unit" for n in X_UNITS_VALID])),
    ("x_wid", 2, frm("dx_reg.wid_out"), to("warp_table.cwid", "ipdom.wid", "barrier_unit.wid", "tensor_unit.wid", "csr.wid",
                                           "wb_mux.wid", "host_if.x_wid")),
    ("x_pc", W, frm("dx_reg.pc_out"), to("valu.pc", "branch_unit.pc", "simt_ctrl.pc", "host_if.x_pc")),
    ("x_tmask", 4, frm("dx_reg.tmask_out"), to("branch_unit.tmask", "vote_shfl.tmask", "simt_ctrl.tmask", "tensor_unit.tmask",
                                               "csr.tmask", "lsu.tmask", "wb_mux.tmask")),
    ("x_rd", 5, frm("dx_reg.rd_out"), to("wb_mux.rd")),
    ("x_alu_op", 4, frm("dx_reg.alu_op_out"), to("valu.alu_op")),
    ("x_a_sel", 1, frm("dx_reg.a_sel_out"), to("valu.a_sel")),
    ("x_b_sel", 1, frm("dx_reg.b_sel_out"), to("valu.b_sel")),
    ("x_wb_src", 3, frm("dx_reg.wb_src_out"), to("wb_mux.wb_src")),
    ("x_regwrite", 1, frm("dx_reg.regwrite_out"), to("wb_mux.regwrite")),
    ("x_ctrl", 2, frm("dx_reg.ctrl_out"), to("branch_unit.ctrl")),
    ("x_br_op", 3, frm("dx_reg.br_op_out"), to("valu.br_op")),
    ("x_mem_store", 1, frm("dx_reg.mem_store_out"), to("lsu.mem_store")),
    ("x_mem_size", 3, frm("dx_reg.mem_size_out"), to("lsu.mem_size")),
    ("x_md_op", 2, frm("dx_reg.md_op_out"), to("vmul.md_op", "vdiv.md_op")),
    ("x_simt_op", 3, frm("dx_reg.simt_op_out"), to("vote_shfl.simt_op", "simt_ctrl.simt_op")),
    ("x_simt_mode", 2, frm("dx_reg.simt_mode_out"), to("vote_shfl.simt_mode")),
    ("x_tensor_op", 2, frm("dx_reg.tensor_op_out"), to("tensor_unit.tensor_op")),
    ("x_csr_addr", 12, frm("dx_reg.csr_addr_out"), to("csr.csr_addr")),
    ("x_illegal", 1, frm("dx_reg.illegal_out"), to("host_if.err_illegal")),
    ("x_imm", W, frm("dx_reg.imm_out"), to("valu.imm", "branch_unit.imm", "lsu.imm")),
    ("x_a", V, frm("dx_reg.a_out"), to("valu.a", "vmul.a", "vdiv.a", "branch_unit.a", "vote_shfl.a", "simt_ctrl.a",
                                       "tensor_unit.a", "lsu.a")),
    ("x_b", V, frm("dx_reg.b_out"), to("valu.b", "vmul.b", "vdiv.b", "vote_shfl.b", "simt_ctrl.b", "tensor_unit.b", "lsu.b")),
    ("alu_y", V, frm("valu.y"), to("wb_mux.alu_y")),
    ("taken", 4, frm("valu.taken"), to("branch_unit.taken")),
    ("mul_y", V, frm("vmul.y"), to("wb_mux.mul_y")),
    ("div_y", V, frm("vdiv.y"), to("wb_mux.div_y")),
    ("div_ready", 1, frm("vdiv.ready"), to("pipe_ctrl.div_ready")),
    ("load_y", V, frm("lsu.y"), to("wb_mux.load_y")),
    ("lsu_ready", 1, frm("lsu.ready"), to("pipe_ctrl.lsu_ready")),
    ("lsu_err", 1, frm("lsu.err"), to("host_if.err_mem")),
    ("simt_y", V, frm("vote_shfl.y"), to("wb_mux.simt_y")),
    ("tensor_y", V, frm("tensor_unit.ld_y"), to("wb_mux.tensor_y")),
    ("tensor_err", 1, frm("tensor_unit.err"), to("host_if.err_tensor")),
    ("csr_y", V, frm("csr.y"), to("wb_mux.csr_y")),
    ("csr_err", 1, frm("csr.err"), to("host_if.err_csr")),
    ("cycle", 48, frm("cycle_ctr.count"), to("csr.cycle")),
    ("br_next_pc", W, frm("branch_unit.next_pc"), to("simt_ctrl.br_next_pc")),
    ("link", W, frm("branch_unit.link"), to("wb_mux.link")),
    ("diverged", 1, frm("branch_unit.diverged"), to("top.diverged")),
    ("c_pc", W, frm("simt_ctrl.c_pc"), to("warp_table.c_pc")),
    ("c_tmask", 4, frm("simt_ctrl.c_tmask"), to("warp_table.c_tmask")),
    ("spawn_mask", 4, frm("simt_ctrl.spawn_mask"), to("warp_table.spawn_mask")),
    ("spawn_pc", W, frm("simt_ctrl.spawn_pc"), to("warp_table.spawn_pc")),
    *[(f"ipd_{f}", w, frm(f"simt_ctrl.{f}"), to(f"ipdom.{f}")) for f, w in
      (("push", 2), ("e0_mask", 4), ("e0_pc", W), ("e0_fall", 1), ("e1_mask", 4), ("e1_pc", W), ("e1_fall", 1), ("pop", 1),
       ("clear", 1))],
    *[(f"top_{f}", w, frm(f"ipdom.top_{f}"), to(f"simt_ctrl.top_{f}")) for f, w in (("mask", 4), ("pc", W), ("fall", 1))],
    ("ipd_depth", 4, frm("ipdom.depth"), to("simt_ctrl.depth")),
    ("bar_arrive", 1, frm("simt_ctrl.bar_arrive"), to("barrier_unit.en")),
    ("bar_id", 2, frm("simt_ctrl.bar_id"), to("barrier_unit.bar_id")),
    ("bar_count", 3, frm("simt_ctrl.bar_count"), to("barrier_unit.bar_count")),
    ("simt_err", 1, frm("simt_ctrl.err"), to("host_if.err_simt")),
    ("advance", 1, frm("pipe_ctrl.advance"), to("warp_table.commit", "ipdom.en", "tensor_unit.advance", "vdiv.advance",
                                                "lsu.advance", "wb_mux.advance", "host_if.advance", "simt_ctrl.advance")),
    *[(f"rf{k}_we", 1, frm(f"wb_mux.we{k}"), to(f"regfile{k}.we")) for k in range(4)],
    ("rf_waddr", 7, frm("wb_mux.waddr"), to(*[f"regfile{k}.waddr" for k in range(4)])),
    *[(f"rf{k}_wdata", W, frm(f"wb_mux.wdata{k}"), to(f"regfile{k}.wdata")) for k in range(4)],

    # memory
    *[(f"lsu_{f}", w, frm(f"lsu.{f}"), to(f"bank_mux.{f}")) for f, w in
      (("g_en", 4), ("g_we", 4), ("g_addr", 36), ("g_wdata", V), ("g_be", 16),
       ("s_en", 4), ("s_we", 4), ("s_addr", 32), ("s_wdata", V), ("s_be", 16))],
    ("g_rdata", V, frm("bank_mux.g_rdata"), to("lsu.g_rdata", "host_if.g_rdata")),
    ("s_rdata", V, frm("bank_mux.s_rdata"), to("lsu.s_rdata", "host_if.s_rdata")),
    *[(f"{sp}b{k}_{f}", w, frm(f"bank_mux.{sp}b{k}_{f}"), to(f"{name}{k}.{f}"))
      for sp, name, abits in (("g", "gbank", 9), ("s", "sbank", 8)) for k in range(4)
      for f, w in (("we", 1), ("addr", abits), ("wdata", W), ("be", 4))],
    *[(f"{sp}b{k}_rdata", W, frm(f"{name}{k}.rdata"), to(f"bank_mux.{sp}b{k}_rdata"))
      for sp, name in (("g", "gbank"), ("s", "sbank")) for k in range(4)],
    ("imem_we", 1, frm("bank_mux.imem_we"), to("imem.we")),
    ("imem_waddr", 9, frm("bank_mux.imem_waddr"), to("imem.waddr")),
    ("imem_wdata", W, frm("bank_mux.imem_wdata"), to("imem.wdata")),
]


def design() -> dict:
    return {
        "id": "simt-gpu",
        "name": "SIMT GPU core v0: 4 warps x 4 lanes, RV32IM + SIMT + INT8 tensor unit",
        "version": 1,
        "createdAt": "2026-10-25T00:00:00.000Z",
        "blocks": BLOCKS,
        "nets": [
            {"id": f"n_{n:03d}", "name": name, "width": width, "driver": {"blockId": d[0], "portId": d[1]},
             "sinks": [{"blockId": blk, "portId": prt} for blk, prt in sinks],
             "kind": "bus" if width > 1 else "wire", "pipelineStage": 0}
            for n, (name, width, d, sinks) in enumerate(WIRES, 1)
        ],
        "topLevelPorts": TOP_PORTS,
        "constraintGroups": [],
        "constraints": [],
        "referenceMaterial": [{
            "id": "isa", "title": "The GPU's instruction set (ISA.md)",
            "source": "demos/simt-gpu/ISA.md, written for this design",
            "blockIds": ["b_decode", "b_simt_ctrl", "b_vote_shfl", "b_tensor_unit", "b_csr", "b_lsu"],
            "content": (HERE / "ISA.md").read_text(encoding="utf-8"),
        }],
    }


def main() -> None:
    write_pipe_golden("sf_reg", SF_FIELDS)
    write_pipe_golden("dx_reg", DX_FIELDS)
    d = design()
    out = HERE / "design.json"
    out.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    print(f"{out}: {len(d['blocks'])} blocks, {len(d['nets'])} nets, {len(d['topLevelPorts'])} top-level ports")


if __name__ == "__main__":
    main()
