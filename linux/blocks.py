"""New blocks of the core with S-mode and an MMU. Golden models: demos/linux-soc/golden/<name>.py.

Group 1, CSRs and traps (replacing the machine-only `csr_file` and `irq_pending`):
  csr_sel2, csr_alu, irq_select, mstatus_reg, trap_unit, csr_mregs, csr_sregs, counters, mip_merge, csr_rmux.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "gpu-soc"))
from build_gpu_soc import block, i, o, port  # noqa: E402

W = 32
CLK, RST = port("p_clk", "clk", "in", 1, "clock"), port("p_rst", "rst", "in", 1, "reset")

SEL_TABLE = """The CSR numbers (sel): 300 hexadecimal mstatus 1, 301 misa 2, 302 medeleg 3, 303 mideleg 4, 304 mie 5, 305 mtvec 6,
    306 mcounteren 7, 340 mscratch 8, 341 mepc 9, 342 mcause 10, 343 mtval 11, 344 mip 12, B00 mcycle 13, B02 minstret 14, B80 mcycleh
    15, B82 minstreth 16, C00 cycle 17, C01 time 18, C02 instret 19, C80 cycleh 20, C81 timeh 21, C82 instreth 22, F11 mvendorid 23,
    F12 marchid 24, F13 mimpid 25, F14 mhartid 26, 100 sstatus 27, 104 sie 28, 105 stvec 29, 106 scounteren 30, 140 sscratch 31,
    141 sepc 32, 142 scause 33, 143 stval 34, 144 sip 35, 180 satp 36, 7A0 tselect 37, 7A1 tdata1 38, 7A2 tdata2 39, 7A3 tdata3 40,
    320 mcountinhibit 41 (these five are hard-wired: they read 0 and ignore writes), 3A0 pmpcfg0 42, 3B0 pmpaddr0 43; every other
    address is 0 (no register)."""

CSROP = """csrop (3 bits) is the instruction's CSR operation: 000 none, 001 CSR read only, 010 CSR write, 011 CSR set bits, 100 CSR clear
    bits, 101 sret, 110 sfence.vma, 111 fence.i."""

CSR_SEL2 = block("b_csr_sel2", "csr_sel2", f"""
    Combinational. The CSR a CSR instruction names, and whether the access is illegal. a is bits 31:20 of inst (the CSR address).
    {SEL_TABLE} sel (6 bits) is the number for a. {CSROP} priv (2 bits) is the privilege level (0 user, 1 supervisor, 3 machine).
    An access is a csrop of 001, 010, 011 or 100; a write is a csrop of 010, 011 or 100. The access is bad when any of these holds:
    sel is 0; priv is less than bits 9:8 of a; it is a write and bits 11:10 of a are 11; sel is 36 (satp) and priv is 1 and tvm is 1;
    sel is a counter (17 to 22) and priv is not 3 and either bit b of mcounteren is 0, or priv is 0 and bit b of scounteren is 0,
    where b is 0 for cycle and cycleh (17, 20), 1 for time and timeh (18, 21) and 2 for instret and instreth (19, 22). illegal is 1
    when the instruction is an access and the access is bad, and 0 otherwise (in particular 0 for every csrop that is not an
    access). No clock, no reset, no state.
""", [i("inst", W), i("csrop", 3, "control"), i("priv", 2, "control"), i("tvm", 1, "control"), i("mcounteren", 3, "control"),
      i("scounteren", 3, "control"), o("sel", 6, "control"), o("illegal", 1, "control")])

CSR_ALU = block("b_csr_alu", "csr_alu", f"""
    Combinational. The value a CSR instruction writes. old is the register's value before the instruction, src the instruction's
    source value (32 bits each). {CSROP} nval is src when csrop is 010, old OR src when csrop is 011, old AND NOT src when csrop
    is 100, and old for every other csrop. No clock, no reset, no state.
""", [i("old", W), i("src", W), i("csrop", 3, "control"), o("nval", W)])

IRQ_SELECT = block("b_irq_select", "irq_select", """
    Combinational. Which interrupt is taken, with delegation to supervisor mode. mip, mie and mideleg are 12 bits each, with an
    interrupt per odd bit: bit 1 supervisor software (SSI), bit 3 machine software (MSI), bit 5 supervisor timer (STI), bit 7 machine
    timer (MTI), bit 9 supervisor external (SEI), bit 11 machine external (MEI); the even bits do not matter. priv is the privilege
    level (2 bits: 0 user, 1 supervisor, 3 machine). An interrupt c is pending when bit c of mip and bit c of mie are both 1. A
    pending interrupt c is enabled when: if bit c of mideleg is 1, priv is 0, or priv is 1 and mstatus_sie is 1; if bit c of mideleg
    is 0, priv is not 3, or mstatus_mie is 1. The interrupts are looked at in the order 11, 3, 7, 9, 1, 5, and the first that is
    pending and enabled is taken: pending is 1 and cause (4 bits) is its number c. When none is, pending is 0 and cause is 0. No
    clock, no reset, no state.
""", [i("mip", 12, "control"), i("mie", 12, "control"), i("mideleg", 12, "control"), i("priv", 2, "control"),
      i("mstatus_mie", 1, "control"), i("mstatus_sie", 1, "control"), o("pending", 1, "control"), o("cause", 4, "control")])

MSTATUS_REG = block("b_mstatus_reg", "mstatus_reg", """
    The privilege level and the mstatus register. Held state: priv (2 bits) and mstatus (32 bits, of which only these bits are held,
    every other bit is always 0: SIE bit 1, MIE bit 3, SPIE bit 5, MPIE bit 7, SPP bit 8, MPP bits 12:11, MPRV bit 17, SUM bit 18,
    MXR bit 19, TVM bit 20, TW bit 21, TSR bit 22). Outputs show the held state: priv, mstatus, and its fields mie (bit 3), sie
    (bit 1), mprv (bit 17), mpp (bits 12:11, 2 bits), sum (bit 18), mxr (bit 19), tvm (bit 20), tw (bit 21), tsr (bit 22).
    On each rising clock edge, the first that applies: rst is 1: priv becomes 3 and mstatus 0. trap_m is 1: MPIE takes the old MIE,
    MIE becomes 0, MPP takes the old priv, priv becomes 3. trap_s is 1: SPIE takes the old SIE, SIE becomes 0, SPP takes bit 0 of
    the old priv, priv becomes 1. mret is 1: priv takes the old MPP, MIE takes the old MPIE, MPIE becomes 1, MPP becomes 0, and when
    the old MPP is not 3, MPRV becomes 0. sret is 1: priv takes the old SPP (0 or 1), SIE takes the old SPIE, SPIE becomes 1, SPP
    becomes 0, MPRV becomes 0. we_m is 1 (a write to mstatus): every held bit takes the same bit of wdata, except that when bits 12:11
    of wdata are 10 MPP keeps its old value. we_s is 1 (a write to sstatus): SIE, SPIE, SPP, SUM and MXR take the same bits of
    wdata and every other held bit keeps its value. Otherwise nothing changes. Fields not named in a case keep their values.
""", [CLK, RST, i("trap_m", 1, "control"), i("trap_s", 1, "control"), i("mret", 1, "control"), i("sret", 1, "control"),
      i("we_m", 1, "control"), i("we_s", 1, "control"), i("wdata", W), o("priv", 2, "control"), o("mstatus", W),
      o("mie", 1, "control"), o("sie", 1, "control"), o("mprv", 1, "control"), o("mpp", 2, "control"), o("sum", 1, "control"),
      o("mxr", 1, "control"), o("tvm", 1, "control"), o("tw", 1, "control"), o("tsr", 1, "control")], reset="sync", latency=1)

TRAP_UNIT = block("b_trap_unit", "trap_unit", f"""
    Combinational. What the write-back stage does with its instruction. valid is 1 for a real instruction. xcpt is 1 when it carries
    an exception or an interrupt, with irq 1 for an interrupt, cause (4 bits) its code, tval (32 bits) its trap value. irq is 1
    only together with xcpt, and then cause is one of the interrupt codes 1, 3, 5, 7, 9 or 11 (0001, 0011, 0101, 0111, 1001, 1011). pc and inst
    are the instruction's address and word. {CSROP} is_mret is 1 for mret. illegal_csr is 1 when its CSR access is illegal. priv
    (2 bits: 0 user, 1 supervisor, 3 machine), tsr and tvm are from mstatus; medeleg (16 bits) and mideleg (12 bits) the
    delegation registers; mtvec, stvec, mepc and sepc (32 bits each) the trap vectors and return addresses.
    illegal is 1 when illegal_csr is 1, or is_mret is 1 and priv is not 3, or csrop is 101 and (priv is 0, or priv is 1 and tsr is
    1), or csrop is 110 and (priv is 0, or priv is 1 and tvm is 1). trap is valid AND (xcpt OR illegal). c is cause when xcpt is 1,
    else 2. is_int is xcpt AND irq. t is 0 when is_int is 1, tval when xcpt is 1 and irq is 0, and inst when xcpt is 0. deleg is 1
    when priv is not 3 and bit c of mideleg (when is_int is 1) or of medeleg (when is_int is 0) is 1. trap_s is trap AND deleg;
    trap_m is trap AND NOT deleg. mret (output) is valid AND NOT trap AND is_mret. sret is valid AND NOT trap AND csrop is 101.
    csr_we is valid AND NOT trap AND csrop is 010, 011 or 100. sfence is valid AND NOT trap AND csrop is 110. refetch is valid AND
    NOT trap AND csrop is 010, 011, 100, 110 or 111. redirect is trap OR mret OR sret OR refetch. kill is trap OR mret OR sret and nothing else: it is NOT redirect, so kill
    is 0 for a CSR refetch (a CSR instruction's own write-back must survive). Example: valid 1, xcpt 0, csrop 011 gives redirect 1
    and kill 0. retire is valid AND NOT trap.
    The vector of a base register v is (v with bits 1:0 cleared) plus 4 times c when is_int is 1 and bit 0 of v is 1, else plus 0
    (32 bits, wrapping). redirect_pc is the vector of mtvec when trap_m is 1; else the vector of stvec when trap_s is 1; else mepc
    when mret is 1; else sepc when sret is 1; else pc plus 4. epc is pc with bit 0 cleared. cause_val (32 bits) is c in bits 3:0
    and is_int in bit 31, 0 elsewhere. tval_out is t. No clock, no reset, no state.
""", [i("valid", 1, "control"), i("xcpt", 1, "control"), i("irq", 1, "control"), i("cause", 4, "control"), i("pc", W, "addr"),
      i("tval", W), i("inst", W), i("csrop", 3, "control"), i("is_mret", 1, "control"), i("illegal_csr", 1, "control"),
      i("priv", 2, "control"), i("tsr", 1, "control"), i("tvm", 1, "control"), i("medeleg", 16, "control"), i("mideleg", 12, "control"),
      i("mtvec", W, "addr"), i("stvec", W, "addr"), i("mepc", W, "addr"), i("sepc", W, "addr"),
      o("redirect", 1, "control"), o("kill", 1, "control"), o("redirect_pc", W, "addr"), o("trap_m", 1, "control"), o("trap_s", 1, "control"),
      o("mret", 1, "control"), o("sret", 1, "control"), o("csr_we", 1, "control"), o("sfence", 1, "control"),
      o("retire", 1, "control"), o("epc", W, "addr"), o("cause_val", W), o("tval_out", W)])

CSR_MREGS = block("b_csr_mregs", "csr_mregs", """
    The machine-mode CSRs other than mstatus and the counters. Held state, all 0 at reset: mtvec, mscratch, mepc, mcause, mtval
    (32 bits each), mie (12 bits), medeleg (16 bits), mideleg (12 bits), mcounteren (3 bits), mip_sw (12 bits, the software-writable
    bits of mip). The outputs show the held values. On each rising clock edge, the first that applies: rst is 1: everything becomes
    0. trap_m is 1: mepc takes epc with bit 0 cleared, mcause takes cause_val and mtval takes tval. we is 1: by sel (6 bits), with v
    the 32-bit value nval: 3: medeleg takes v AND B3FF hexadecimal; 4: mideleg takes v AND 222; 5: mie takes v AND AAA; 6: mtvec takes
    v with bit 1 cleared; 7: mcounteren takes bits 2:0 of v; 8: mscratch takes v; 9: mepc takes v with bit 0 cleared; 10: mcause
    takes v; 11: mtval takes v; 12: mip_sw takes (mip_sw AND 200 hexadecimal) OR (v AND 22 hexadecimal) (bit 9, the software-writable SEIP bit, is never changed by a write: a read-modify-write of mip would otherwise copy the external interrupt line into it); 28 (sie): mie takes (mie AND NOT mideleg) OR (v AND mideleg AND 222);
    35 (sip): mip_sw takes (mip_sw AND NOT (mideleg AND 2)) OR (v AND mideleg AND 2); any other sel changes nothing. Otherwise
    nothing changes.
""", [CLK, RST, i("sel", 6, "control"), i("we", 1, "control"), i("nval", W), i("trap_m", 1, "control"), i("epc", W, "addr"),
      i("cause_val", W), i("tval", W), o("mtvec", W, "addr"), o("mscratch", W), o("mepc", W, "addr"), o("mcause", W), o("mtval", W),
      o("mie", 12, "control"), o("medeleg", 16, "control"), o("mideleg", 12, "control"), o("mcounteren", 3, "control"),
      o("mip_sw", 12, "control")], reset="sync", latency=1)

CSR_SREGS = block("b_csr_sregs", "csr_sregs", """
    The supervisor CSRs. Held state, all 0 at reset: stvec, sscratch, sepc, scause, stval, satp (32 bits each) and scounteren (3
    bits). The outputs show the held values. On each rising clock edge, the first that applies: rst is 1: everything becomes 0.
    trap_s is 1: sepc takes epc with bit 0 cleared, scause takes cause_val and stval takes tval. we is 1: by sel (6 bits), with v
    the 32-bit value nval: 29: stvec takes v with bit 1 cleared; 30: scounteren takes bits 2:0 of v; 31: sscratch takes v; 32: sepc
    takes v with bit 0 cleared; 33: scause takes v; 34: stval takes v; 36: satp takes v AND 803FFFFF hexadecimal; any other sel
    changes nothing. Otherwise nothing changes.
""", [CLK, RST, i("sel", 6, "control"), i("we", 1, "control"), i("nval", W), i("trap_s", 1, "control"), i("epc", W, "addr"),
      i("cause_val", W), i("tval", W), o("stvec", W, "addr"), o("sscratch", W), o("sepc", W, "addr"), o("scause", W), o("stval", W),
      o("satp", W), o("scounteren", 3, "control")], reset="sync", latency=1)

COUNTERS = block("b_counters", "counters", """
    The cycle and retired-instruction counters, 64 bits each, both 0 at reset. Held state: mcycle and minstret (64 bits each). On each
    rising clock edge the first that applies: rst is 1: both become 0. we is 1 (a CSR write in write-back) and sel (6 bits) names a
    counter, with nval (32 bits) the value written: sel 13 writes the low word of mcycle, sel 15 its high word, sel 14 the low word of
    minstret, sel 16 its high word; the written word takes nval, the other word keeps its value, and the counter does not count on
    this edge (a write to minstret suppresses the increment of the instruction that writes it). Any other sel with we: nothing is
    written, and the counters count as below. Otherwise: mcycle goes up by one and minstret goes up by one when retire is 1 (both wrap
    at 64 bits). The outputs mcycle and minstret show the held values.
""", [CLK, RST, i("retire", 1, "control"), i("we", 1, "control"), i("sel", 6, "control"), i("nval", W), o("mcycle", 64), o("minstret", 64)],
      reset="sync", latency=1)

MIP_MERGE = block("b_mip_merge", "mip_merge", """
    Combinational. The mip register as read (12 bits): bits 1, 5 and 9 are bits 1, 5 and 9 of mip_sw; bit 11 is meip, bit 7 is mtip,
    bit 3 is msip; every other bit is 0. No clock, no reset, no state.
""", [i("mip_sw", 12, "control"), i("meip", 1, "control"), i("mtip", 1, "control"), i("msip", 1, "control"), o("mip", 12, "control")])

CSR_RMUX = block("b_csr_rmux", "csr_rmux", f"""
    Combinational. The value a CSR reads, by its number sel (6 bits). {SEL_TABLE} rdata (32 bits): 1 mstatus; 2 the constant
    40141105 hexadecimal (misa); 3 medeleg; 4 mideleg; 5 mie; 6 mtvec; 7 mcounteren; 8 mscratch; 9 mepc; 10 mcause; 11 mtval; 12 mip;
    13 bits 31:0 of mcycle; 14 bits 31:0 of minstret; 15 bits 63:32 of mcycle; 16 bits 63:32 of minstret; 17 bits 31:0 of mcycle; 18
    bits 31:0 of mtime; 19 bits 31:0 of minstret; 20 bits 63:32 of mcycle; 21 bits 63:32 of mtime; 22 bits 63:32 of minstret; 23, 24
    and 25 the constant 0; 26 hartid; 27 mstatus AND 000C0122 hexadecimal (sstatus); 28 mie AND mideleg (sie); 29 stvec; 30
    scounteren; 31 sscratch; 32 sepc; 33 scause; 34 stval; 35 mip AND mideleg (sip); 36 satp; 42 pmpcfg0; 43 pmpaddr0 (both from
    the PMP registers, the inputs pmpcfg0 and pmpaddr0 of 32 bits); any other sel 0. Inputs narrower than
    32 bits are zero-extended. Widths: mcycle, minstret and mtime 64 bits; medeleg 16; mideleg, mie and mip 12; mcounteren and
    scounteren 3; hartid 2; the others 32. No clock, no reset, no state.
""", [i("sel", 6, "control"), i("mstatus", W), i("medeleg", 16, "control"), i("mideleg", 12, "control"), i("mie", 12, "control"),
      i("mtvec", W), i("mcounteren", 3, "control"), i("mscratch", W), i("mepc", W), i("mcause", W), i("mtval", W),
      i("mip", 12, "control"), i("mcycle", 64), i("minstret", 64), i("mtime", 64), i("hartid", 2, "control"), i("stvec", W),
      i("scounteren", 3, "control"), i("sscratch", W), i("sepc", W), i("scause", W), i("stval", W), i("satp", W),
      i("pmpcfg0", W), i("pmpaddr0", W), o("rdata", W)])

GROUP1 = [CSR_SEL2, CSR_ALU, IRQ_SELECT, MSTATUS_REG, TRAP_UNIT, CSR_MREGS, CSR_SREGS, COUNTERS, MIP_MERGE, CSR_RMUX]
BLOCKS = GROUP1

# ---------------------------------------------------------------------------------------------------------------- group 2: the MMU
FLAGS = "flags are the low 8 bits of a page-table entry: V bit 0, R bit 1, W bit 2, X bit 3, U bit 4, G bit 5, A bit 6, D bit 7"

TLB = block("b_tlb", "tlb", f"""
    Translation lookaside buffer with 8 entries, fully associative. Each entry holds valid (1 bit), vpn (20 bits), ppn (22 bits),
    mega (1 bit) and flags (8 bits); {FLAGS}. A pointer ptr (3 bits) names the entry the next fill writes. At reset every entry is
    invalid (all its fields 0) and ptr is 0. Lookup, combinational from the held entries and va (32 bits), whose page number is
    vpn = bits 31:12 of va: an entry matches when it is valid and, if its mega is 1, bits 19:10 of its vpn equal bits 19:10 of vpn
    (bits 31:22 of va), and if its mega is 0, its vpn equals vpn. When some entry matches, the lowest-numbered matching entry gives:
    hit 1; ppa (20 bits) is (bits 19:10 of its ppn, then bits 9:0 of vpn, which are bits 21:12 of va) when its mega is 1 and bits 19:0 of its ppn when its mega is 0; flags its flags. When none
    matches, hit, ppa and flags are 0. On each rising clock edge, the first that applies: rst is 1: every entry becomes invalid and
    ptr 0. flush is 1: every entry becomes invalid and ptr 0. fill is 1: the entry ptr takes valid 1, vpn fill_vpn, ppn fill_ppn, mega
    fill_mega and flags fill_flags, and ptr goes up by one (wrapping from 7 to 0). Otherwise nothing changes.
""", [CLK, RST, i("flush", 1, "control"), i("fill", 1, "valid"), i("fill_vpn", 20, "addr"), i("fill_ppn", 22, "addr"),
      i("fill_mega", 1, "control"), i("fill_flags", 8, "control"), i("va", W, "addr"), o("hit", 1, "control"), o("ppa", 20, "addr"),
      o("flags", 8, "control")], reset="sync", latency=1)

PERM_CHECK = block("b_perm_check", "perm_check", f"""
    Combinational. Whether an access is refused by a leaf page-table entry. kind (2 bits): 00 instruction fetch, 01 load, 10 or 11
    store. priv (2 bits): 0 user, 1 supervisor, 3 machine. sum and mxr are the mstatus bits. {FLAGS}. fault is 1 when any of these
    holds, else 0. A machine-mode access (priv 3) never faults here: machine mode does not translate, so fault is 0 whatever the flags.
    Otherwise fault is 1 when any of these holds: priv is 0 and U is 0; priv is 1 and U is 1 and (kind is a fetch or sum is 0); the access is not allowed (a fetch
    needs X; a load needs R, or X when mxr is 1; a store needs W); A is 0; the access is a store and D is 0. No clock, no reset, no state.
""", [i("kind", 2, "control"), i("priv", 2, "control"), i("sum", 1, "control"), i("mxr", 1, "control"), i("flags", 8, "control"),
      o("fault", 1, "control")])

PTW = block("b_ptw", "ptw", """
    Page-table walker for Sv32. Held state, all 0 at reset: st (IDLE 0, L1 1, L0 2), a (34 bits, the address of the entry to read),
    va (32 bits), fault (1), facc (1), fvpn (20). The address a is in RAM when bits 33:26 of a are 00100000.
    Outputs: busy is 1 when st is not IDLE. fault, fault_access and fault_vpn show the held fault, facc and fvpn exactly, as they are
    before the edge: they do not depend on this cycle's inputs (clear, start and the rest do not change them until the edge). When st is L1 or L0 and a is in RAM: req is 1 and addr is bits 31:0 of a; otherwise req and
    addr are 0. The entry read is pte = rdata (32 bits) when req and grant are both 1; its fields: V bit 0, R bit 1, W bit 2, X bit 3,
    ppn bits 31:10 (22 bits). fill is 1 when req is 1, grant is 1, V is 1, not (R is 0 and W is 1), (R or X) is 1, and not (st is L1
    and bits 9:0 of ppn are not 0); then fill_vpn is bits 31:12 of va, fill_ppn is ppn, fill_mega is 1 when st is L1 (else 0), and
    fill_flags is bits 7:0 of pte. When fill is 0, fill_vpn, fill_ppn, fill_mega and fill_flags are 0.
    On each rising clock edge: when rst is 1 everything becomes 0 (IDLE). Otherwise first, when clear is 1: fault becomes 0 and a walk
    in progress is abandoned (st becomes IDLE; start is ignored on that edge; this is how a redirect cancels the walk of an instruction
    it squashed). Otherwise by st (fvpn is always bits 31:12 of the held va, never of vaddr): IDLE: when start is 1, va takes vaddr, a takes satp_ppn times 4096 plus (bits 31:22 of vaddr) times 4, fault becomes 0 and st
    becomes L1 (when start is 0 nothing else changes). L1 or L0 with a not in RAM, or with deny 1 (the physical memory protection refuses the read): st becomes IDLE, fault 1, facc 1, fvpn bits 31:12 of
    va. L1 or L0 with a in RAM and grant 0: nothing changes. L1 or L0 with a in RAM and grant 1, by pte: when V is 0, or R is 0 and W is
    1: st IDLE, fault 1, facc 0, fvpn bits 31:12 of va. Else when R or X is 1 (a leaf): when st is L1 and bits 9:0 of ppn are not 0: st
    IDLE, fault 1, facc 0, fvpn bits 31:12 of va; otherwise st IDLE (the entry is delivered by fill). Else (a pointer) when st is L0, or when bit 7, bit 6 or bit 4 of pte (D, A, U: reserved in a pointer) is 1:
    st IDLE, fault 1, facc 0, fvpn bits 31:12 of va. Else (a pointer at L1): st becomes L0 and a takes ppn times 4096 plus (bits 21:12
    of va) times 4.
""", [CLK, RST, i("start", 1, "control"), i("vaddr", W, "addr"), i("satp_ppn", 22, "addr"), i("grant", 1, "control"), i("rdata", W),
      i("clear", 1, "control"), i("deny", 1, "control"), o("busy", 1, "control"), o("req", 1, "control"), o("addr", W, "addr"), o("fill", 1, "valid"),
      o("fill_vpn", 20, "addr"), o("fill_ppn", 22, "addr"), o("fill_mega", 1, "control"), o("fill_flags", 8, "control"),
      o("fault", 1, "control"), o("fault_access", 1, "control"), o("fault_vpn", 20, "addr")], reset="sync", latency=1)

XFAULT = block("b_xfault", "xfault", """
    Combinational. The result of one address translation. hit, and perm_fault (the access is refused by the entry that hit); wfault,
    waccess and wvpn (20 bits) are the walker's held fault, whether it was an access fault, and the page it was for; va (32 bits) is
    this lookup's address. held is wfault AND (wvpn equals bits 31:12 of va). pf is perm_fault when hit is 1, and held AND NOT waccess when hit is 0.
    af is NOT hit AND held AND waccess. miss is NOT hit AND NOT held. No clock, no reset, no state.
""", [i("hit", 1, "control"), i("perm_fault", 1, "control"), i("wfault", 1, "control"), i("waccess", 1, "control"),
      i("wvpn", 20, "addr"), i("va", W, "addr"), o("pf", 1, "control"), o("af", 1, "control"), o("miss", 1, "control")])

PA_MUX = block("b_pa_mux", "pa_mux", """
    Combinational. The physical address. When xlate is 1, pa is ppa (20 bits) in bits 31:12 and bits 11:0 of va in bits 11:0; when
    xlate is 0, pa is va. No clock, no reset, no state.
""", [i("xlate", 1, "control"), i("va", W, "addr"), i("ppa", 20, "addr"), o("pa", W, "addr")])

XLATE_ON = block("b_xlate_on", "xlate_on", """
    Combinational. Whether addresses are translated. priv (2 bits: 0 user, 1 supervisor, 3 machine); mprv and mpp (2 bits) from
    mstatus; satp_mode is bit 31 of satp. dpriv (2 bits), the privilege of data accesses, is mpp when mprv is 1 and priv is 3, and priv
    otherwise. xlate_i is 1 when satp_mode is 1 and priv is not 3. xlate_d is 1 when satp_mode is 1 and dpriv is not 3. kind_i (2 bits) is always 00 (the access kind of an instruction fetch). No clock, no
    reset, no state.
""", [i("priv", 2, "control"), i("mprv", 1, "control"), i("mpp", 2, "control"), i("satp_mode", 1, "control"),
      o("xlate_i", 1, "control"), o("xlate_d", 1, "control"), o("dpriv", 2, "control"), o("kind_i", 2, "control")])

DKIND = block("b_dkind", "dkind", """
    Combinational, in the execute stage. valid is 1 for a real instruction; memsrc 01 means a load; memwrite 1 a store; is_amo 1 an
    atomic instruction, amo_op (4 bits) its code (0001 is load-reserved). access is 1 when valid is 1 and (memsrc is 01 or memwrite is
    1 or is_amo is 1). store is 1 when memwrite is 1, or is_amo is 1 and amo_op is not 0001. kind (2 bits) is 10 when store is 1
    and 01 otherwise. No clock, no reset, no state.
""", [i("valid", 1, "control"), i("memsrc", 2, "control"), i("memwrite", 1, "control"), i("is_amo", 1, "control"),
      i("amo_op", 4, "control"), o("access", 1, "control"), o("store", 1, "control"), o("kind", 2, "control")])

DFAULT_GATE = block("b_dfault_gate", "dfault_gate", """
    Combinational, in the execute stage. The data translation looks up the result address of every instruction, but only an instruction
    that reads or writes memory can fault on it, and only while data accesses are translated. access is 1 when the instruction does (dkind's access).
    xlate is 1 when data accesses are translated. pf and af are the translation's page fault and access fault for the instruction's result
    address. pf_o is 1 when pf is 1 and access is 1 and xlate is 1, and 0 otherwise; af_o is 1 when af is 1 and access is 1 and xlate is 1, and 0
    otherwise. No clock, no reset, no state.
""", [i("access", 1, "control"), i("xlate", 1, "control"), i("pf", 1, "control"), i("af", 1, "control"), o("pf_o", 1, "control"), o("af_o", 1, "control")])

MMU_CTL = block("b_mmu_ctl", "mmu_ctl", """
    Combinational. Whether the core must wait for a page-table walk, and what to walk. need_hi is 1 when bit 1 of pc is 1 and bits
    17:16 of word_lo (the word fetched at pc) are 11: the instruction continues into the next word. lm is xlate_i AND lo_miss. hm is xlate_i AND
    NOT lo_miss AND need_hi AND hi_miss. dm is xlate_d AND d_access AND d_miss. stall is ptw_busy OR lm OR hm OR dm. walk_start is NOT
    ptw_busy AND (lm OR hm OR dm). walk_va (32 bits) is d_va when dm is 1; else pc when lm is 1; else hi_addr when hm is 1; else 0.
    No clock, no reset, no state.
""", [i("xlate_i", 1, "control"), i("xlate_d", 1, "control"), i("d_access", 1, "control"), i("word_lo", W),
      i("lo_miss", 1, "control"), i("hi_miss", 1, "control"), i("d_miss", 1, "control"), i("ptw_busy", 1, "control"),
      i("pc", W, "addr"), i("hi_addr", W, "addr"), i("d_va", W, "addr"), o("stall", 1, "control"), o("walk_start", 1, "control"),
      o("walk_va", W, "addr")])

IFAULT = block("b_ifault", "ifault", """
    Combinational, after the fetch aligner. A fetch that faulted enters the pipeline as a reserved instruction word. inst (32 bits)
    and is16 are the aligner's output; pc is the fetch address; word_lo the word read at pc; xlate is 1 when fetches are translated;
    lo_pf and lo_af say the word at pc gave a page fault or an access fault, hi_pf and hi_af the same for the next word. need_hi is 1
    when bit 1 of pc is 1 and bits 17:16 of word_lo are 11. When xlate is 1 and (lo_pf or lo_af is 1): inst_out is 0000000B
    hexadecimal with bits 14:12 set to 001 when lo_pf is 1, else 010 (that is 0000100B or 0000200B), and is16_out is 0. Else when
    xlate is 1 and need_hi is 1 and (hi_pf or hi_af is 1): inst_out is the reserved word with bits 14:12 001 when hi_pf is 1, else
    010, and bit 20 also 1 (0010100B or 0010200B; nothing of word_lo or inst is copied into it), and is16_out is 0. Otherwise inst_out is inst and is16_out is is16. No clock, no
    reset, no state.
""", [i("inst", W), i("is16", 1, "control"), i("pc", W, "addr"), i("word_lo", W), i("xlate", 1, "control"), i("lo_pf", 1, "control"),
      i("lo_af", 1, "control"), i("hi_pf", 1, "control"), i("hi_af", 1, "control"), o("inst_out", W), o("is16_out", 1, "control")])

LANE_SIGS = (("addr", W), ("store_data", W), ("memtype", 3), ("memsrc", 2), ("valid", 1), ("xcpt", 1), ("memwrite", 1), ("kill", 1),
             ("dmem_we", 1), ("dmem_wdata", W))
LANE_MUX = block("b_lane_mux", "lane_mux", """
    Combinational. A core's lane on the shared bus, which its page-table walker takes while it walks. The core's memory-stage
    signals are addr, store_data and dmem_wdata (32 bits each), memtype (3), memsrc (2), valid, xcpt, memwrite, kill and dmem_we (1
    each), and core_req, its request for the bus. Each output <name>_o: when busy is 1, addr_o is ptw_addr, memtype_o is 010,
    memsrc_o is 01, valid_o is 1, and store_data_o, xcpt_o, memwrite_o, kill_o, dmem_we_o and dmem_wdata_o are 0, and req is ptw_req.
    When busy is 0, each <name>_o is the input <name>, and req is core_req AND NOT stall. No clock, no reset, no state.
""", [i("busy", 1, "control"), i("ptw_req", 1, "control"), i("ptw_addr", W, "addr"), i("stall", 1, "control"),
      i("core_req", 1, "control")] + [i(n, w, "addr" if n == "addr" else "control" if w <= 3 else "data") for n, w in LANE_SIGS] +
     [o(f"{n}_o", w, "addr" if n == "addr" else "control" if w <= 3 else "data") for n, w in LANE_SIGS] + [o("req", 1, "control")])

EN_AND = block("b_en_and", "en_and", """
    Combinational. en is 1 when run is 1 and stall is 0, and 0 otherwise. No clock, no reset, no state.
""", [i("run", 1, "control"), i("stall", 1, "control"), o("en", 1, "control")])

WLANE = block("b_wlane", "wlane", """
    Combinational. A store's bytes on their lanes of a 32-bit word, with byte enables (bit k of be for bits 8k+7:8k). memtype (3
    bits): 000 and 011 a byte, 001 and 100 a half-word, 101 no access, 010, 110 and 111 a word. With a = bits 1:0 of addr: a byte: be
    has only bit a set and data is bits 7:0 of wdata shifted left by 8 times a; a half-word: with h = bit 1 of addr, be is 0011 when h
    is 0 and 1100 when h is 1, and data is bits 15:0 of wdata shifted left by 16 times h; a word: be is 1111 and data is wdata; no
    access: be and data are 0. Bits of data not on an enabled lane are 0. No clock, no reset, no state.
""", [i("memtype", 3, "control"), i("addr", W, "addr"), i("wdata", W), o("be", 4, "control"), o("data", W)])

SYS_DECODE = block("b_sys_decode", "sys_decode", """
    Combinational decoder for the instructions that are illegal, trap or touch the control and status registers, for a core with
    user, supervisor and machine modes. inst is the 32-bit instruction word; priv (2 bits) is the privilege level (0 user, 1
    supervisor, 3 machine; 2 is treated as 3). The word is LEGAL when bits 1:0 are 11 and it matches one of these (opcode is bits 6:0,
    funct3 bits 14:12, funct7 bits 31:25): LUI (opcode 0110111), AUIPC (0010111) and JAL (1101111) with any other bits; JALR
    (1100111) with funct3 000; a branch (1100011) with funct3 000, 001, 100, 101, 110 or 111; a load (0000011) with funct3 000, 001,
    010, 100 or 101; a store (0100011) with funct3 000, 001 or 010; an immediate arithmetic instruction (0010011) with funct3 000,
    010, 011, 100, 110 or 111 and any upper bits, with funct3 001 and funct7 0000000, or with funct3 101 and funct7 0000000 or
    0100000; a register arithmetic instruction (0110011) with funct7 0000000 and any funct3, with funct7 0100000 and funct3 000 or
    101, or with funct7 0000001 and any funct3; a fence (opcode 0001111, funct3 000) or fence.i (opcode 0001111, funct3 001); an
    atomic instruction (opcode 0101111) with funct3 010 and bits 31:27 equal to 00000, 00001, 00011, 00100, 01000, 01100, 10000,
    10100, 11000 or 11100 (bits 26:25 may be anything), or with bits 31:27 equal to 00010 and bits 24:20 equal to 00000; a system
    instruction (1110011) with funct3 000 that is exactly one of five words: 00000073 hexadecimal (ecall), 00100073 (ebreak),
    30200073 (mret), 10200073 (sret), 10500073 (wfi), or that is sfence.vma: funct7 0001001, bits 11:7 00000 and funct3 000 (bits
    24:15 may be anything); a system instruction with funct3 001, 010, 011, 101, 110 or 111 (the six CSR instructions, bits 31:20 are
    the CSR address and bits 19:15 the source register or immediate); or a fetch-fault word: opcode 0001011 with funct3 001 or 010
    (every other bit may be anything). Every other word is illegal.
    Outputs, the first case that applies: an illegal word: xcpt 1, cause 2 (ILLEGAL_INSTRUCTION). A fetch-fault word: xcpt 1, cause
    12 (1100) when funct3 is 001 and cause 1 when funct3 is 010. ebreak: xcpt 1, cause 3. ecall: xcpt 1, cause 8 when priv is 0, 9
    when priv is 1, 11 when priv is 2 or 3. sret: csrop 101. sfence.vma: csrop 110. fence.i: csrop 111. A CSR instruction: is_csr 1;
    csr_imm is funct3 bit 2; csrop is 010 (CSR_WRITE) when funct3 bits 1:0 are 01, 011 (CSR_SET) when they are 10 and bits 19:15
    are not zero, 100 (CSR_CLEAR) when they are 11 and bits 19:15 are not zero, and 001 (CSR_READ) when they are 10 or 11 and bits
    19:15 are zero. Every output a case does not name is 0 (xcpt, cause, csrop, csr_imm, is_csr); fence, wfi, mret and the atomics
    have them all 0. Independently of those cases: is_mret is 1 only for the word 30200073. is_amo is 1 for a legal atomic
    instruction, and amo_op is then, by bits 31:27: 00010 AMO_LR (0001), 00011 AMO_SC (0010), 00001 AMO_SWAP (0011), 00000 AMO_ADD
    (0100), 00100 AMO_XOR (0101), 01100 AMO_AND (0110), 01000 AMO_OR (0111), 10000 AMO_MIN (1000), 10100 AMO_MAX (1001), 11000
    AMO_MINU (1010), 11100 AMO_MAXU (1011); for every other word is_amo and amo_op are 0. No clock, no reset, no state.
""", [i("inst", W), i("priv", 2, "control"), o("xcpt", 1, "control"), o("cause", 4, "control"), o("csrop", 3, "control"),
      o("csr_imm", 1, "control"), o("is_csr", 1, "control"), o("is_mret", 1, "control"), o("is_amo", 1, "control"),
      o("amo_op", 4, "control")])

EX_XCPT = block("b_ex_xcpt", "ex_xcpt", """
    Combinational exception unit for the execute stage of a core with an MMU. It adds the exceptions the execute stage finds to the
    one decode may already have raised, and decides the trap value. id_xcpt and id_cause (4 bits) are decode's exception; id_irq is 1
    when that is really an interrupt. inst and pc are the instruction and its address. memtype (3 bits) is the access type (101 when
    the instruction is not a load or store), memwrite is 1 for a store, alu_y is the (virtual) address of the access. d_pf and d_af say
    the access gave a page fault or an access fault in translation, and d_store says it counts as a store. A memory access is
    misaligned when memtype is 010, 110 or 111 and bits 1:0 of alu_y are not 00, or memtype is 001 or 100 and bit 0 of alu_y is 1;
    memtype 000, 011 and 101 are never misaligned. The first that applies: (1) id_xcpt is 1: xcpt 1, cause id_cause; tval is 0 when
    id_irq is 1; otherwise inst when id_cause is 2, pc when it is 3, pc plus 2 (32 bits, wrapping) when id_cause is 12 or 1 and bit 20
    of inst is 1, pc when id_cause is 12 or 1 and bit 20 of inst is 0, and 0 for any other cause. (2) misaligned: xcpt 1, cause 6 when
    d_store is 1 and 4 otherwise, tval alu_y. (3) d_pf is 1: xcpt 1, cause 15 when d_store is 1 and 13 otherwise, tval alu_y. (4) d_af
    is 1: xcpt 1, cause 7 when d_store is 1 and 5 otherwise, tval alu_y. (5) otherwise xcpt, cause and tval are 0. memwrite_out is 0
    when xcpt is 1 and memwrite otherwise. No clock, no reset, no state.
""", [i("id_xcpt", 1, "control"), i("id_cause", 4, "control"), i("id_irq", 1, "control"), i("inst", W), i("pc", W, "addr"),
      i("memtype", 3, "control"), i("memwrite", 1, "control"), i("alu_y", W, "addr"), i("d_pf", 1, "control"), i("d_af", 1, "control"),
      i("d_store", 1, "control"), o("xcpt", 1, "control"), o("cause", 4, "control"), o("tval", W), o("memwrite_out", 1, "control")])

IMEM2 = {**block("b_imem2", "imem2", """
    The instruction memory of one core: a copy of the 64 MB RAM (16777216 words of 32 bits, word k at byte address 4k), read at two
    addresses at once and written whenever the RAM is written. raddr and raddr2 are byte addresses; the word read is picked by their
    bits 25:2 (bits 31:26 and 1:0 are ignored); rdata and rdata2 show those words at once (asynchronous reads). On each rising clock
    edge when we is 1, the word picked by bits 25:2 of waddr takes, in each byte lane k (bits 8k+7:8k) whose be bit k is 1, the same
    bits of wdata; lanes whose be bit is 0 keep their value. A read of the word being written in the same cycle shows the old value.
    The initial contents are loaded from a file; reset does not change them.
""", [CLK, i("we", 1, "control"), i("waddr", W, "addr"), i("wdata", W), i("be", 4, "control"), i("raddr", W, "addr"), o("rdata", W),
      i("raddr2", W, "addr"), o("rdata2", W)]),
         "storage": {"kind": "memory", "depth": 16777216, "readStyle": "async", "sameCycle": "old", "initial": "file", "resetClears": False,
                     "zeroReg": False, "addrLow": 2, "addrHigh": "ignored",
                     "ports": {"we": "p_we", "wdata": "p_wdata", "waddr": "p_waddr", "raddr": "p_raddr", "rdata": "p_rdata",
                               "raddr2": "p_raddr2", "rdata2": "p_rdata2", "be": "p_be"}}}

STATUS_WE = block("b_status_we", "status_we", """
    Combinational. The write strobes of mstatus and sstatus. we_m is 1 when csr_we is 1 and sel (6 bits) is 1; we_s is 1 when csr_we
    is 1 and sel is 27; both are 0 otherwise. No clock, no reset, no state.
""", [i("csr_we", 1, "control"), i("sel", 6, "control"), o("we_m", 1, "control"), o("we_s", 1, "control")])

SATP_SPLIT = block("b_satp_split", "satp_split", """
    Combinational. The fields of satp (32 bits): mode is bit 31; ppn (22 bits) is bits 21:0. No clock, no reset, no state.
""", [i("satp", W), o("mode", 1, "control"), o("ppn", 22, "addr")])

GROUP2 = [STATUS_WE, SATP_SPLIT, TLB, PERM_CHECK, PTW, XFAULT, PA_MUX, XLATE_ON, DKIND, DFAULT_GATE, MMU_CTL, IFAULT, LANE_MUX, EN_AND, WLANE, SYS_DECODE, EX_XCPT]
RLOAD = block("b_rload", "rload", """
    Combinational. The value a load takes from the word the RAM read at its address. word (32 bits) is that word; memtype (3 bits) is
    the access type: 000 a byte, sign-extended; 001 a half-word, sign-extended; 010 a word; 011 a byte, zero-extended; 100 a
    half-word, zero-extended; 101 no access (the result is 0); 110 and 111 act as a word. addr (2 bits) is bits 1:0 of the access
    address (bits 1:0 are used): a byte is the byte at 8 times bits 1:0 of addr, a half-word is the half at 16 times bit 1 of addr. rdata (32 bits) is the result.
    No clock, no reset, no state.
""", [i("word", 32), i("memtype", 3, "control"), i("addr", 32, "addr"), o("rdata", 32)])

PACK4 = block("b_pack4", "pack4", """
    Combinational. Four 22-bit word addresses (a0 to a3) as one 88-bit bus: bits 21:0 are a0, bits 43:22 a1, bits 65:44 a2, bits
    87:66 a3. bus88 is that bus. No clock, no reset, no state.
""", [i("a0", 22, "addr"), i("a1", 22, "addr"), i("a2", 22, "addr"), i("a3", 22, "addr"), o("bus88", 88, "addr")])

UNPACK4 = block("b_unpack4", "unpack4", """
    Combinational. A 128-bit bus (bus128) of four 32-bit words: bits 31:0 are w0, bits 63:32 w1, bits 95:64 w2, bits 127:96 w3. No clock, no
    reset, no state.
""", [i("bus128", 128, "data"), o("w0", 32), o("w1", 32), o("w2", 32), o("w3", 32)])

WORD_ADDR = block("b_word_addr", "word_addr", """
    Combinational. The RAM word address of a byte address: addr (32 bits) is bits 23:2 of it, as word (22 bits). No clock, no reset,
    no state.
""", [i("addr", 32, "addr"), o("word", 22, "addr")])

KILL_GATE = block("b_kill_gate", "kill_gate", """
    Combinational. Two kill inputs. kill_wb is 1 when a trap or mret is taken: it cancels the register write of the instruction in
    write-back (regwrite_out is regwrite when kill_wb is 0 and 0 when kill_wb is 1). kill_mem is 1 for any redirect, including a
    CSR refetch: it cancels the memory write of the instruction in the memory stage (memwrite_out is memwrite when kill_mem is 0 and
    0 when kill_mem is 1). The instruction in write-back keeps its register write on a CSR refetch; the instructions behind it do not
    keep a memory write. No clock, no reset, no state.
""", [i("regwrite", 1, "control"), i("memwrite", 1, "control"), i("kill_wb", 1, "control"), i("kill_mem", 1, "control"),
      o("regwrite_out", 1, "control"), o("memwrite_out", 1, "control")])

PMP_REGS = block("b_pmp_regs", "pmp_regs", """
    The physical memory protection registers that exist so far: pmpcfg0 (32 bits, four entry configurations) and pmpaddr0 (32 bits).
    Both are held state, 0 at reset. On each rising clock edge: rst is 1: both become 0. Otherwise, when we is 1 and sel (6 bits) is 42,
    pmpcfg0 takes nval (32 bits); when we is 1 and sel is 43, pmpaddr0 takes nval; any other case keeps its value. The outputs show the
    held values. Access checks are not part of this block.
""", [CLK, RST, i("we", 1, "control"), i("sel", 6, "control"), i("nval", W), o("pmpcfg0", W), o("pmpaddr0", W)], reset="sync", latency=1)

PACK16 = block("b_pack16", "pack16", """
    Combinational. Sixteen 22-bit word addresses (a0 to a15) as one 352-bit bus: a0 in bits 21:0, a1 in bits 43:22, and so on, a15 in
    bits 351:330. bus352 is that bus. No clock, no reset, no state.
""", [i(f"a{k}", 22, "addr") for k in range(16)] + [o("bus352", 352, "addr")])

UNPACK16 = block("b_unpack16", "unpack16", """
    Combinational. A 512-bit bus (bus512) of sixteen 32-bit words: w0 in bits 31:0, w1 in bits 63:32, and so on, w15 in bits 511:480.
    No clock, no reset, no state.
""", [i("bus512", 512, "data")] + [o(f"w{k}", 32) for k in range(16)])

GROUP3 = [RLOAD, PACK4, UNPACK4, WORD_ADDR, KILL_GATE, PMP_REGS, PACK16, UNPACK16]
BLOCKS = GROUP1 + GROUP2 + GROUP3   # imem2 (a 64 MB copy per core) is not generated: fetch reads the shared RAM through a second read port


CSR_HW = block("b_csr_hw", "csr_hw", """
    Combinational. Maps the CSR addresses of the hard-wired performance, endianness and environment-configuration registers (they read 0 and ignore writes)
    onto number 44, after the CSR decoder. inst (32 bits) is an instruction; a is its bits 31:20 (the CSR address). sel_in (6 bits) and ill_in (1 bit) are the
    decoder's number and illegal flag. csrop (3 bits) is 000 none, 001 CSR read only, 010 CSR write, 011 CSR set bits, 100 CSR clear bits, other values not a
    CSR access; priv (2 bits) is the privilege level (3 machine). pmp is 1 when a is from 3A1 to 3A3 or from 3B1 to 3BF (hexadecimal, bounds included; 3A0 and 3B0 already have numbers). hw is 1 when a is 310, 30A, 31A or 10A hexadecimal, or from 323 to 33F, or from B03 to B1F,
    or from B83 to B9F, or from C03 to C1F, or from C83 to C9F (all hexadecimal, bounds included). When sel_in is 0 and hw is 1: sel_out is 44 and ill_out is 1
    when csrop is 001, 010, 011 or 100 and priv is not 3, or when csrop is 010, 011 or 100 and bits 11:10 of a are 11 (a read-only address written), else 0.
    When sel_in is 0 and pmp is 1: sel_out is 42 when a is from 3A1 to 3A3 and 43 when a is from 3B1 to 3BF, and ill_out is 1 when csrop is 001, 010, 011 or 100 and priv is not 3, else 0.
    In every other case sel_out is sel_in and ill_out is ill_in. No clock, no reset, no state.
""", [i("inst", W), i("csrop", 3, "control"), i("priv", 2, "control"), i("sel_in", 6, "control"), i("ill_in", 1, "control"),
      o("sel_out", 6, "control"), o("ill_out", 1, "control")])
BLOCKS = BLOCKS + [CSR_HW]


PMP_REGS16 = block("b_pmp_regs16", "pmp_regs16", """
    The physical memory protection registers: sixteen entry configurations cfg0 to cfg15 (8 bits each) and sixteen entry addresses addr0 to addr15 (32
    bits each), all held state, 0 at reset. The CSR access: we is 1 in a cycle a CSR instruction writes, inst (32 bits) is that instruction (a is its bits
    31:20, the CSR address), sel (6 bits) is the decoder's CSR number, nval (32 bits) the value written. wr is 1 when we is 1 and sel is 42, 43 or 45.
    pmpcfgN (N from 0 to 3, address 3A0 hexadecimal plus N) holds the configurations of entries 4N to 4N+3, entry 4N+j in bits 8j+7:8j. pmpaddrN (N from 0 to 15,
    address 3B0 hexadecimal plus N) is addr N. On each rising clock edge: rst is 1: everything becomes 0. Otherwise, when wr is 1 and a is the address of
    pmpcfgN: for each j from 0 to 3, entry e is 4N+j and b is bits 8j+7:8j of nval; when bit 7 of cfg e is 1 (locked) cfg e keeps its value; otherwise, when
    bit 0 of b is 0 and bit 1 of b is 1 (reserved combination) cfg e keeps its value; otherwise cfg e becomes b AND 9F hexadecimal (bits 6 and 5 stay 0).
    When wr is 1 and a is the address of pmpaddrN: addr N becomes nval unless bit 7 of cfg N is 1, or N is less than 15 and cfg N+1 has bit 7 equal to 1 and
    bits 4:3 equal to 01 (a locked TOR entry above): then it keeps its value. Output rdata (32 bits), combinational from the held state and a: for a from 3A0
    to 3A3 the four configurations of pmpcfgN as stored (entry 4N+j in bits 8j+7:8j), for a from 3B0 to 3BF the addr N, and 0 for any other a. Outputs cfg_all (128
    bits: cfg0 in bits 7:0, cfg1 in bits 15:8, and so on, cfg15 in bits 127:120) and addr_all (512 bits: addr0 in bits 31:0, addr1 in bits 63:32, and so on, addr15 in
    bits 511:480) show the held values.
""", [CLK, RST, i("we", 1, "control"), i("inst", W), i("sel", 6, "control"), i("nval", W), o("rdata", W), o("cfg_all", 128, "data"),
      o("addr_all", 512, "data")], reset="sync", latency=1)

PMP_CHECK = block("b_pmp_check", "pmp_check", """
    Combinational. Whether the physical memory protection refuses an access. pa (32 bits) is the physical address, kind (2 bits) is 00 for an instruction fetch,
    01 for a load and 10 or 11 for a store or atomic, priv (2 bits) is the privilege level of the access (0 user, 1 supervisor, 3 machine), en (1 bit) says the
    access happens (when en is 0, deny is 0). cfg_all (128 bits) holds sixteen 8-bit entry configurations (entry i in bits 8i+7:8i) and addr_all (512 bits) sixteen
    32-bit entry addresses (entry i in bits 32i+31:32i). Let w be bits 31:2 of pa as an unsigned number. For entry i, c is its configuration, mode is bits 4:3 of c, and
    prev is the address of entry i-1 (0 for entry 0). Entry i matches when: mode is 1 and prev is not greater than w and w is less than addr i (unsigned);
    or mode is 2 and w equals addr i; or mode is 3 and (w AND NOT m) equals (addr i AND NOT m) where m is addr i XOR (addr i plus 1) taken in 32 bits; mode 0
    never matches. The entry allows the access when: kind is 00 and bit 2 of c is 1; or kind is 01 and bit 0 of c is 1; or kind is 10 or 11 and bit 1 of c is 1.
    The lowest-numbered entry that matches decides: deny is 1 when (priv is not 3 or bit 7 of c (locked) is 1) and the entry does not allow the access, else 0. When no entry
    matches, deny is 1 when priv is not 3 and 0 when priv is 3. deny is 0 whenever en is 0. No clock, no reset, no state.
""", [i("pa", W, "addr"), i("kind", 2, "control"), i("priv", 2, "control"), i("en", 1, "control"), i("cfg_all", 128, "data"), i("addr_all", 512, "data"),
      o("deny", 1, "control")])
BLOCKS = BLOCKS + [PMP_REGS16, PMP_CHECK]


PMP_K = block("b_pmp_k", "pmp_k", """
    Combinational. Constants and a kind code for the physical memory protection checks. store (1 bit) is 1 for a store or atomic access. kind_f (2 bits) is 00
    (binary). kind_d (2 bits) is 10 (binary) when store is 1 and 01 (binary) when store is 0. kind_l (2 bits) is 01 (binary) and priv_s (2 bits) is 01 (binary). one (1 bit) is 1. No clock, no reset, no state.
""", [i("store", 1, "control"), o("kind_f", 2, "control"), o("kind_d", 2, "control"), o("kind_l", 2, "control"), o("priv_s", 2, "control"), o("one", 1, "control")])
BLOCKS = BLOCKS + [PMP_K]


IFAULT_PMP = block("b_ifault_pmp", "ifault_pmp", """
    Combinational, after the fetch aligner. A fetch that faulted enters the pipeline as a reserved instruction word. inst (32 bits)
    and is16 are the aligner's output; pc is the fetch address; word_lo the word read at pc; xlate is 1 when fetches are translated;
    lo_pf and lo_af say the word at pc gave a page fault or an access fault in translation, hi_pf and hi_af the same for the next word. pmp_lo and pmp_hi say the
    physical memory protection refuses the fetch of the word at pc and of the next word (these count whether or not fetches are translated). need_hi is 1
    when bit 1 of pc is 1 and bits 17:16 of word_lo are 11 (binary). The fault word is built from fields: bits 6:0 are 0001011 (binary), bits 14:12 are 001 (binary)
    for a page fault and 010 (binary) for an access fault, bit 20 is 1 when the fault is of the next word (hi) and 0 when it is of the word at pc, and every other
    bit is 0. The first case that applies: (1) xlate is 1 and lo_pf is 1: inst_out is the fault word for a page fault of the word at pc, and is16_out is 0.
    (2) (xlate is 1 and lo_af is 1) or pmp_lo is 1: inst_out is the fault word for an access fault of the word at pc, and is16_out is 0. (3) xlate is 1 and need_hi
    is 1 and hi_pf is 1: inst_out is the fault word for a page fault of the next word, and is16_out is 0. (4) need_hi is 1 and ((xlate is 1 and hi_af is 1) or
    pmp_hi is 1): inst_out is the fault word for an access fault of the next word, and is16_out is 0. (5) otherwise inst_out is inst and is16_out is is16.
    No clock, no reset, no state.
""", [i("inst", W, "data"), i("is16", 1, "control"), i("pc", W, "data"), i("word_lo", W, "data"), i("xlate", 1, "control"), i("lo_pf", 1, "control"),
      i("lo_af", 1, "control"), i("hi_pf", 1, "control"), i("hi_af", 1, "control"), i("pmp_lo", 1, "control"), i("pmp_hi", 1, "control"),
      o("inst_out", W, "data"), o("is16_out", 1, "control")])
BLOCKS = BLOCKS + [IFAULT_PMP]
