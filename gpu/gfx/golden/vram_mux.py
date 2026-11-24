"""Golden model of the video-memory write-port switch (block `vram_mux`). Combinational. Never shown to the generator.

While running is 1 the raster-output unit owns the write ports: bank k (0..3) gets m_we<k> = r_we<k>, m_waddr<k> = r_waddr<k>,
m_wdata<k> = r_wdata<k>. While running is 0 the host does: m_we<k> = v_we<k>, m_waddr<k> = v_waddr, and m_wdata<k> = v_wdata_lo
for banks 0 and 2, v_wdata_hi for banks 1 and 3.
"""


def golden_vram_mux(running, v_we0, v_we1, v_we2, v_we3, v_waddr, v_wdata_lo, v_wdata_hi,
                    r_we0, r_we1, r_we2, r_we3, r_waddr0, r_waddr1, r_waddr2, r_waddr3,
                    r_wdata0, r_wdata1, r_wdata2, r_wdata3):
    v_we, r_we = (v_we0, v_we1, v_we2, v_we3), (r_we0, r_we1, r_we2, r_we3)
    r_waddr, r_wdata = (r_waddr0, r_waddr1, r_waddr2, r_waddr3), (r_wdata0, r_wdata1, r_wdata2, r_wdata3)
    out = {}
    for k in range(4):
        if running & 1:
            out[f"m_we{k}"], out[f"m_waddr{k}"], out[f"m_wdata{k}"] = r_we[k] & 1, r_waddr[k], r_wdata[k]
        else:
            out[f"m_we{k}"], out[f"m_waddr{k}"] = v_we[k] & 1, v_waddr
            out[f"m_wdata{k}"] = v_wdata_lo if k % 2 == 0 else v_wdata_hi
    return out
