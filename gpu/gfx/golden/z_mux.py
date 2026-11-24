"""Golden model of the depth memory's write-port switch (block `z_mux`). Combinational. Never shown to the generator.

While running is 1 the depth unit owns the four write ports: mz_we<k> = zw_we<k>, mz_waddr<k> = zw_waddr<k>, mz_wdata<k> = zw_wdata<k>.
While running is 0 the host does: mz_we<k> = zh_we<k>, mz_waddr<k> = zh_waddr, mz_wdata<k> = zh_wdata_lo for banks 0 and 2 and
zh_wdata_hi for banks 1 and 3.
"""


def golden_z_mux(running, zh_we0, zh_we1, zh_we2, zh_we3, zh_waddr, zh_wdata_lo, zh_wdata_hi, zw_we0, zw_we1, zw_we2, zw_we3,
                 zw_waddr0, zw_waddr1, zw_waddr2, zw_waddr3, zw_wdata0, zw_wdata1, zw_wdata2, zw_wdata3):
    if running & 1:
        we, wa, wd = [zw_we0, zw_we1, zw_we2, zw_we3], [zw_waddr0, zw_waddr1, zw_waddr2, zw_waddr3], [zw_wdata0, zw_wdata1, zw_wdata2, zw_wdata3]
    else:
        we, wa, wd = [zh_we0, zh_we1, zh_we2, zh_we3], [zh_waddr] * 4, [zh_wdata_lo, zh_wdata_hi, zh_wdata_lo, zh_wdata_hi]
    return {**{f"mz_we{k}": we[k] for k in range(4)}, **{f"mz_waddr{k}": wa[k] for k in range(4)}, **{f"mz_wdata{k}": wd[k] for k in range(4)}}
