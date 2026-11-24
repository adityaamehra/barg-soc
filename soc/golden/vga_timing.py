"""Golden model of `vga_timing`: 640x480 VGA timing from a pixel tick every 4th clock (800x525 total). Clocked. Written by hand. None before the first reset."""


def golden_vga_timing(trace):
    st = None
    out = []
    for i in trace:
        if st is None:
            out.append({k: None for k in ("de", "hs", "vs", "vbl", "frame", "widx", "half")})
        else:
            div, hc, vc = st
            active = hc < 640 and vc < 480
            out.append({"de": int(active and bool(i["enable"] & 1)), "hs": int(not (656 <= hc < 752)), "vs": int(not (490 <= vc < 492)), "vbl": int(vc >= 480),
                        "frame": int(div == 3 and hc == 799 and vc == 524), "widx": ((vc >> 1) * 160 + (hc >> 2)) & 0xFFFF, "half": hc >> 1 & 1})
        if i["rst"] & 1:
            st = (0, 0, 0)
        elif st is not None:
            div, hc, vc = st
            if div == 3:
                if hc == 799:
                    hc, vc = 0, (0 if vc == 524 else vc + 1)
                else:
                    hc += 1
            st = ((div + 1) & 3, hc, vc)
    return out


def traces(rng):
    out = []
    for _ in range(6):     # short: the first pixels, with enable toggling and the odd reset
        t = [{"rst": 1, "enable": 0}]
        for _ in range(3000):
            t.append({"rst": int(rng.random() < 0.0005), "enable": int(rng.random() < 0.9)})
        out.append(t)
    # one long trace: two whole pictures are not needed; one picture and a bit reaches every wrap (hc 799 -> 0, vc 524 -> 0, the sync pulses, the blanking)
    t = [{"rst": 1, "enable": 0}]
    for c in range(800 * 525 * 4 + 20000):
        t.append({"rst": 0, "enable": int((c // 1000) % 7 != 0)})
    out.append(t)
    return out
