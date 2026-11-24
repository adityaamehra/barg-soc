"""Golden model of the instruction decoder of `simt-gpu-gfx` (gfx/build_gfx.py, block `decode`): the GPU core's decoder (../golden/decode.py)
plus the graphics instructions of opcode custom-2 (0x5B), all with funct7 = 0: gfx.cfg (funct3 0) and pix (5), legal with rd = 0 only,
regwrite 0; rast (1), rast.edge (3), tex (4) and ztest (6), legal with any registers, regwrite 1 (their result reaches the register
file through the ALU source, wb_src ALU). They set the new output gfx = 1 and leave unit NONE (7), so no other unit acts on them.
funct3 2 and 7 are illegal. gfx_op = funct3 always, as tensor_op.

Written by hand from the block's description, never shown to the pipeline. Combinational.
Fields copied from the instruction every time: rs1 = bits 19:15, rs2 = 24:20, rd = 11:7, csr_addr = 31:20, br_op = mem_size =
funct3, md_op = funct3 bits 1:0, simt_op = funct3, simt_mode = funct7 bits 1:0, tensor_op = funct3 bits 1:0.
The other outputs (and gfx, default 0) follow the instruction's class; an output the class does not mention has its default:
unit NONE (7), alu_op ADD (0), a_sel 0, b_sel 0, immsel NO_IMMEDIATE (5), wb_src ALU (0), regwrite 0, ctrl NONE (0),
mem_store 0, illegal 0. An illegal instruction has every default with illegal = 1.
"""

ALU, MUL, DIV, LSU, SIMT, TENSOR, CSR, NONE = range(8)
ADD, SUB, SLL, SLT, SLTU, XOR, SRL, SRA, OR, AND, PASS_B = range(11)
WB_ALU, WB_MUL, WB_DIV, WB_LOAD, WB_SIMT, WB_TENSOR, WB_CSR, WB_LINK = range(8)
IMM_I, IMM_S, IMM_B, IMM_U, IMM_J, IMM_NONE = range(6)
C_NONE, C_BRANCH, C_JAL, C_JALR = range(4)


def golden_decode(inst):
    inst &= 0xFFFFFFFF
    op, rd, f3, rs1, rs2, f7 = inst & 0x7F, inst >> 7 & 31, inst >> 12 & 7, inst >> 15 & 31, inst >> 20 & 31, inst >> 25
    out = {"rs1": rs1, "rs2": rs2, "rd": rd, "csr_addr": inst >> 20, "br_op": f3, "mem_size": f3, "md_op": f3 & 3,
           "simt_op": f3, "simt_mode": f7 & 3, "tensor_op": f3 & 3, "gfx_op": f3}
    d = {"unit": NONE, "alu_op": ADD, "a_sel": 0, "b_sel": 0, "immsel": IMM_NONE, "wb_src": WB_ALU, "regwrite": 0,
         "ctrl": C_NONE, "mem_store": 0, "illegal": 0, "gfx": 0}

    def ok(**kw):
        d.update(kw)

    if op == 0x37:                                            # LUI
        ok(unit=ALU, alu_op=PASS_B, b_sel=1, immsel=IMM_U, regwrite=1)
    elif op == 0x17:                                          # AUIPC
        ok(unit=ALU, alu_op=ADD, a_sel=1, b_sel=1, immsel=IMM_U, regwrite=1)
    elif op == 0x6F:                                          # JAL
        ok(unit=ALU, a_sel=1, b_sel=1, immsel=IMM_J, wb_src=WB_LINK, regwrite=1, ctrl=C_JAL)
    elif op == 0x67 and f3 == 0:                              # JALR
        ok(unit=ALU, b_sel=1, immsel=IMM_I, wb_src=WB_LINK, regwrite=1, ctrl=C_JALR)
    elif op == 0x63 and f3 not in (2, 3):                     # branches
        ok(unit=ALU, immsel=IMM_B, ctrl=C_BRANCH)
    elif op == 0x03 and f3 in (0, 1, 2, 4, 5):                # loads
        ok(unit=LSU, b_sel=1, immsel=IMM_I, wb_src=WB_LOAD, regwrite=1)
    elif op == 0x23 and f3 in (0, 1, 2):                      # stores
        ok(unit=LSU, b_sel=1, immsel=IMM_S, mem_store=1)
    elif op == 0x13:                                          # OP-IMM
        table = {0: ADD, 2: SLT, 3: SLTU, 4: XOR, 6: OR, 7: AND}
        if f3 in table:
            ok(unit=ALU, alu_op=table[f3], b_sel=1, immsel=IMM_I, regwrite=1)
        elif f3 == 1 and f7 == 0:
            ok(unit=ALU, alu_op=SLL, b_sel=1, immsel=IMM_I, regwrite=1)
        elif f3 == 5 and f7 in (0, 0x20):
            ok(unit=ALU, alu_op=SRL if f7 == 0 else SRA, b_sel=1, immsel=IMM_I, regwrite=1)
        else:
            d["illegal"] = 1
    elif op == 0x33:                                          # OP
        if f7 == 0:
            ok(unit=ALU, alu_op=[ADD, SLL, SLT, SLTU, XOR, SRL, OR, AND][f3], regwrite=1)
        elif f7 == 0x20 and f3 in (0, 5):
            ok(unit=ALU, alu_op=SUB if f3 == 0 else SRA, regwrite=1)
        elif f7 == 1:
            ok(unit=MUL if f3 < 4 else DIV, wb_src=WB_MUL if f3 < 4 else WB_DIV, regwrite=1)
        else:
            d["illegal"] = 1
    elif op == 0x0F:                                          # FENCE, FENCE.I: nothing to do
        pass
    elif op == 0x73:                                          # SYSTEM: CSR reads only
        if f3 in (2, 3, 6, 7) and rs1 == 0:
            ok(unit=CSR, wb_src=WB_CSR, regwrite=1)
        else:
            d["illegal"] = 1
    elif op == 0x0B:                                          # SIMT
        if (f3 <= 4 and f7 == 0) or (f3 == 5 and f7 <= 2) or (f3 == 6 and f7 <= 3):
            ok(unit=SIMT, wb_src=WB_SIMT, regwrite=1 if f3 in (5, 6) else 0)
        else:
            d["illegal"] = 1
    elif op == 0x2B and f7 == 0 and f3 <= 3:                  # tensor
        fields_ok = {0: rd == 0, 1: True, 2: rd == 0, 3: rd == 0 and rs1 == 0 and rs2 == 0}[f3]
        if fields_ok:
            ok(unit=TENSOR, wb_src=WB_TENSOR, regwrite=1 if f3 == 1 else 0)
        else:
            d["illegal"] = 1
    elif op == 0x5B and f7 == 0 and rd == 0 and f3 in (0, 5):  # graphics: gfx.cfg, pix
        ok(gfx=1)
    elif op == 0x5B and f7 == 0 and f3 in (1, 3, 4, 6):         # graphics with a result: rast, rast.edge, tex, ztest
        ok(gfx=1, regwrite=1)
    else:
        d["illegal"] = 1
    out.update(d)
    return out


def _r(op, rd, f3, rs1, rs2, f7):
    return f7 << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | rd << 7 | op


def vectors(rng):
    """Directed vectors: every instruction class (RV32I, M, CSR reads, fence, SIMT, tensor) with random registers and
    immediates, and every illegal variation of an opcode's funct3 and funct7. Random 32-bit words are almost all illegal."""
    out = []
    ops = [0x37, 0x17, 0x6F, 0x67, 0x63, 0x03, 0x23, 0x13, 0x33, 0x0F, 0x73, 0x0B, 0x2B, 0x5B]
    for op in ops:
        for f3 in range(8):
            for f7 in (0, 1, 2, 0x20, 0x7F, rng.randrange(128)):
                for _ in range(3):
                    out.append({"inst": _r(op, rng.randrange(32), f3, rng.randrange(32), rng.randrange(32), f7)
                                | (rng.getrandbits(12) << 20 if op in (0x13, 0x03, 0x67, 0x73) and f7 not in (0, 0x20) else 0)})
                # rd = 0 and rs1 = rs2 = 0 forms: some classes (gfx.cfg, pix, tensor, CSR reads) are legal only with them
                out.append({"inst": _r(op, 0, f3, rng.randrange(32), rng.randrange(32), f7)})
                out.append({"inst": _r(op, 0, f3, 0, 0, f7)})
                out.append({"inst": _r(op, rng.randrange(32), f3, 0, rng.randrange(32), f7)})
    for f3 in range(8):                                       # graphics: rd != 0 with rs1 = rs2 = 0 and with any registers
        for f7 in (0, 0, 1, 0x40):
            out.append({"inst": _r(0x5B, 1 + rng.randrange(31), f3, 0, 0, f7)})
            out.append({"inst": _r(0x5B, 1 + rng.randrange(31), f3, rng.randrange(32), rng.randrange(32), f7)})
    for op in range(128):                                     # every opcode once, so an opcode constant cannot be wrong unseen
        out.append({"inst": _r(op, 0, rng.randrange(8), rng.randrange(32), rng.randrange(32), 0)})
    for _ in range(300):
        out.append({"inst": rng.getrandbits(32)})
    return out
