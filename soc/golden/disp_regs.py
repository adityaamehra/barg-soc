"""Golden model of `disp_regs`: enable bit, size constant, frame counter. Clocked. Written by hand. None before the first reset."""
M32 = 0xFFFFFFFF


def golden_disp_regs(trace):
    st = None
    out = []
    for i in trace:
        if st is None:
            out.append({"rdata": None, "enable": None})
        else:
            en, fr = st
            sel = i["addr"] >> 2 & 3
            rd = {0: (i["vbl"] & 1) << 8 | en, 1: 0x00F00140, 2: fr, 3: 0}[sel]
            out.append({"rdata": rd, "enable": en})
        if i["rst"] & 1:
            st = (0, 0)
        elif st is not None:
            en, fr = st
            if i["we"] & 1 and (i["addr"] >> 2 & 3) == 0:
                en = i["wdata"] & 1
            if i["frame"] & 1:
                fr = (fr + 1) & M32
            st = (en, fr)
    return out


def traces(rng):
    out = []
    for _ in range(40):
        t = [{"rst": 1, "we": 0, "addr": 0, "wdata": 0, "frame": 0, "vbl": 0}]
        for _ in range(200):
            t.append({"rst": int(rng.random() < 0.005), "we": int(rng.random() < 0.4), "addr": rng.getrandbits(32), "wdata": rng.getrandbits(32),
                      "frame": int(rng.random() < 0.2), "vbl": rng.getrandbits(1)})
        out.append(t)
    return out
