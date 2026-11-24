"""Golden model of the video memory's read-address switch (block `vram_rmux`). Combinational. Never shown to the generator.

While running is 1 the raster-output unit reads the work copy (for blending): m_raddr<k> = r_raddr<k> for bank k = 0..3. While
running is 0 the host does: every m_raddr<k> = vw_raddr.
"""


def golden_vram_rmux(running, vw_raddr, r_raddr0, r_raddr1, r_raddr2, r_raddr3):
    r = [r_raddr0, r_raddr1, r_raddr2, r_raddr3]
    return {f"m_raddr{k}": r[k] if running & 1 else vw_raddr for k in range(4)}
