"""Golden model of the write-back selector (block `wb_mux`). Combinational.

w = advance & regwrite & (rd != 0); r = the source wb_src selects: 0 alu_y, 1 mul_y, 2 div_y, 3 load_y, 4 simt_y, 5 tensor_y,
6 csr_y, 7 link in every lane. For each lane k: we_k = w & tmask bit k, wdata_k = lane k of r. waddr = wid * 32 + rd.
"""


def golden_wb_mux(advance, regwrite, rd, wid, tmask, wb_src, alu_y, mul_y, div_y, load_y, simt_y, tensor_y, csr_y, link):
    link4 = sum((link & 0xFFFFFFFF) << 32 * i for i in range(4))
    data = [alu_y, mul_y, div_y, load_y, simt_y, tensor_y, csr_y, link4][wb_src & 7]
    w = int(bool(advance & 1 and regwrite & 1 and rd & 31))
    out = {"waddr": (wid & 3) * 32 + (rd & 31)}
    for k in range(4):
        out[f"we{k}"] = w & (tmask >> k & 1)
        out[f"wdata{k}"] = data >> 32 * k & 0xFFFFFFFF
    return out
