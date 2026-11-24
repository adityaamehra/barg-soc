"""Golden model of the graphics host-bus side (block `gfx_host`). Clocked, synchronous reset. Never shown to the generator.

Video memory window: host_addr bits 31:18 == 0x1000, bits 17:0 < 0x25800, bits 1:0 == 0. A word holds pixel p = bits 17:1 (low
half) and p + 1 (high half); banks 0/1 when bit 2 is 0, banks 2/3 when bit 2 is 1, index bits 17:3.
Combinational: v_waddr = vw_raddr = host_addr bits 17:3; v_wdata_lo/hi = host_wdata halves; v_we0/1 = wr & !bit2,
v_we2/3 = wr & bit2 with wr = host_en & host_we & in window; disp_en = its register.
host_rdata from the registered raddr: window -> {vw_rdata1, vw_rdata0} or {vw_rdata3, vw_rdata2} by bit 2; 0x3000_0020 ->
disp_en; 0x3000_0024 -> frame << 8 | vblank; else core_rdata.
Edge: rst -> raddr = 0, disp_en = 0. Else raddr = host_addr; a write to 0x3000_0020 sets disp_en = host_wdata bit 0.
"""

M = 0xFFFFFFFF
OUTS = ("v_we0", "v_we1", "v_we2", "v_we3", "v_waddr", "v_wdata_lo", "v_wdata_hi", "vw_raddr", "host_rdata", "disp_en")


def in_window(a):
    return (a >> 18) == 0x1000 and (a & 0x3FFFF) < 0x25800 and a & 3 == 0


class GfxHost:
    def __init__(self):
        self.r = None

    def outputs(self, i):
        a = i["host_addr"] & M
        wr = bool(i["host_en"] & 1 and i["host_we"] & 1 and in_window(a))
        hi = a >> 2 & 1
        out = {"v_we0": int(wr and not hi), "v_we1": int(wr and not hi), "v_we2": int(wr and hi), "v_we3": int(wr and hi),
               "v_waddr": a >> 3 & 0x7FFF, "vw_raddr": a >> 3 & 0x7FFF,
               "v_wdata_lo": i["host_wdata"] & 0xFFFF, "v_wdata_hi": i["host_wdata"] >> 16 & 0xFFFF}
        if self.r is None:
            out.update(host_rdata=None, disp_en=None)
            return out
        ra = self.r["raddr"]
        if in_window(ra):
            lo, hi_ = (i["vw_rdata2"], i["vw_rdata3"]) if ra >> 2 & 1 else (i["vw_rdata0"], i["vw_rdata1"])
            data = (hi_ & 0xFFFF) << 16 | (lo & 0xFFFF)
        elif ra == 0x3000_0020:
            data = self.r["disp_en"]
        elif ra == 0x3000_0024:
            data = (i["frame"] & 0xFF) << 8 | (i["vblank"] & 1)
        else:
            data = i["core_rdata"] & M
        out.update(host_rdata=data, disp_en=self.r["disp_en"])
        return out

    def edge(self, i):
        if i["rst"] & 1:
            self.r = {"raddr": 0, "disp_en": 0}
            return
        if self.r is None:
            return
        a = i["host_addr"] & M
        r = {"raddr": a, "disp_en": self.r["disp_en"]}
        if i["host_en"] & 1 and i["host_we"] & 1 and a == 0x3000_0020:
            r["disp_en"] = i["host_wdata"] & 1
        self.r = r


def golden_gfx_host(trace):
    m, out = GfxHost(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out
