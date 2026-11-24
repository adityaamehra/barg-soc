"""Golden model of the operand stage (block `operand`). Combinational.

Each lane k has its own register file of 128 words (word = wid x 32 + register). raddr1 = wid * 32 + rs1,
raddr2 = wid * 32 + rs2. a gathers rdata1_k into lane k (bits 32k+31..32k), or is 0 when rs1 is 0; b likewise from rdata2_k,
or 0 when rs2 is 0 (register x0 reads 0 in every warp, whatever the register files hold).
"""

M = 0xFFFFFFFF


def golden_operand(wid, rs1, rs2, rdata1_0, rdata1_1, rdata1_2, rdata1_3, rdata2_0, rdata2_1, rdata2_2, rdata2_3):
    a = sum((v & M) << 32 * k for k, v in enumerate((rdata1_0, rdata1_1, rdata1_2, rdata1_3)))
    b = sum((v & M) << 32 * k for k, v in enumerate((rdata2_0, rdata2_1, rdata2_2, rdata2_3)))
    return {"raddr1": (wid & 3) * 32 + (rs1 & 31), "raddr2": (wid & 3) * 32 + (rs2 & 31),
            "a": 0 if rs1 & 31 == 0 else a, "b": 0 if rs2 & 31 == 0 else b}
