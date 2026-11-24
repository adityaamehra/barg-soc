"""Golden model of the display controller (block `disp_ctrl`). Clocked, synchronous reset. Never shown to the generator.

VGA 640 x 480 @ 60 Hz: 800 clocks a line (640 visible, 16 front porch, 96 sync, 48 back porch), 525 lines a frame (480, 10, 2,
33). The 320 x 240 image is doubled in both directions; image pixel p = y*320 + x is in bank p mod 4 at index p / 4.
Registers hc, vc (10), frame (8), d_hc, d_vc (10), d_on (1), all 0 after reset.
Edge: rst -> all 0. enable 0 -> hc = vc = 0, d_on = 0. enable 1 -> d_hc = hc, d_vc = vc, d_on = 1; hc steps to 799 then wraps,
vc steps at the wrap to 524 then wraps and frame increments (mod 256).
Combinational: vd_raddr = (vc >> 1) * 80 + (hc >> 3) inside 640 x 480, else 0; vblank = vc >= 480; vis = d_on & d_hc < 640 &
d_vc < 480; de = vis; rgb = vd_rdata[(d_hc >> 1) & 3] when vis else 0; hsync = 0 when d_on & 656 <= d_hc < 752; vsync = 0 when
d_on & 490 <= d_vc < 492 (active low).
"""

OUTS = ("vd_raddr", "hsync", "vsync", "de", "rgb", "vblank", "frame")


class DispCtrl:
    def __init__(self):
        self.r = None

    def outputs(self, i):
        if self.r is None:
            return {k: None for k in OUTS}
        r = self.r
        hc, vc = r["hc"], r["vc"]
        vis = r["d_on"] and r["d_hc"] < 640 and r["d_vc"] < 480
        return {
            "vd_raddr": (vc >> 1) * 80 + (hc >> 3) if hc < 640 and vc < 480 else 0,
            "vblank": int(vc >= 480),
            "frame": r["frame"],
            "de": int(vis),
            "rgb": i[f"vd_rdata{(r['d_hc'] >> 1) & 3}"] & 0xFFFF if vis else 0,
            "hsync": 0 if r["d_on"] and 656 <= r["d_hc"] < 752 else 1,
            "vsync": 0 if r["d_on"] and 490 <= r["d_vc"] < 492 else 1,
        }

    def edge(self, i):
        if i["rst"] & 1:
            self.r = {k: 0 for k in ("hc", "vc", "frame", "d_hc", "d_vc", "d_on")}
            return
        if self.r is None:
            return
        r = dict(self.r)
        if not i["enable"] & 1:
            r.update(hc=0, vc=0, d_on=0)
        else:
            r.update(d_hc=r["hc"], d_vc=r["vc"], d_on=1)
            if r["hc"] == 799:
                r["hc"] = 0
                if r["vc"] == 524:
                    r["vc"] = 0
                    r["frame"] = (r["frame"] + 1) & 0xFF
                else:
                    r["vc"] += 1
            else:
                r["hc"] += 1
        self.r = r


def golden_disp_ctrl(trace):
    m, out = DispCtrl(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out
