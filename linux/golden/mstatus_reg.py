"""Golden model of `mstatus_reg`: the privilege level and the mstatus fields. Clocked. Written by hand (iss_s.py's take_trap, mret,
sret and mstatus/sstatus writes). mstatus bits: SIE 1, MIE 3, SPIE 5, MPIE 7, SPP 8, MPP 12:11, MPRV 17, SUM 18, MXR 19, TVM 20, TW 21,
TSR 22; every other bit reads 0. At reset priv is 3 (M) and every field is 0."""

MASK = (1 << 1 | 1 << 3 | 1 << 5 | 1 << 7 | 1 << 8 | 3 << 11 | 1 << 17 | 1 << 18 | 1 << 19 | 1 << 20 | 1 << 21 | 1 << 22)
SMASK = 1 << 1 | 1 << 5 | 1 << 8 | 1 << 18 | 1 << 19


class St:
    def __init__(self):
        self.priv, self.st = None, None

    def outputs(self):
        if self.st is None:
            return {k: None for k in ("priv", "mstatus", "mie", "sie", "mprv", "mpp", "sum", "mxr", "tvm", "tw", "tsr")}
        s = self.st
        return {"priv": self.priv, "mstatus": s, "mie": s >> 3 & 1, "sie": s >> 1 & 1, "mprv": s >> 17 & 1, "mpp": s >> 11 & 3,
                "sum": s >> 18 & 1, "mxr": s >> 19 & 1, "tvm": s >> 20 & 1, "tw": s >> 21 & 1, "tsr": s >> 22 & 1}

    def edge(self, i):
        if i["rst"] & 1:
            self.priv, self.st = 3, 0
            return
        if self.st is None:
            return
        s, p = self.st, self.priv
        if i["trap_m"] & 1:
            s = (s & ~(1 << 7)) | ((s >> 3 & 1) << 7)
            s = (s & ~(1 << 3) & ~(3 << 11)) | (p << 11)
            p = 3
        elif i["trap_s"] & 1:
            s = (s & ~(1 << 5)) | ((s >> 1 & 1) << 5)
            s = (s & ~(1 << 1) & ~(1 << 8)) | ((p & 1) << 8)
            p = 1
        elif i["mret"] & 1:
            mpp = s >> 11 & 3
            s = (s & ~(1 << 3)) | ((s >> 7 & 1) << 3) | 1 << 7
            s &= ~(3 << 11)
            if mpp != 3:
                s &= ~(1 << 17)
            p = mpp
        elif i["sret"] & 1:
            spp = s >> 8 & 1
            s = (s & ~(1 << 1)) | ((s >> 5 & 1) << 1) | 1 << 5
            s &= ~(1 << 8)
            s &= ~(1 << 17)
            p = spp
        elif i["we_m"] & 1:
            w = i["wdata"]
            mpp = w >> 11 & 3
            w = (w & ~(3 << 11)) | ((mpp if mpp != 2 else s >> 11 & 3) << 11)
            s = w & MASK
        elif i["we_s"] & 1:
            s = (s & ~SMASK) | (i["wdata"] & SMASK)
        self.st, self.priv = s & 0xFFFFFFFF, p


def golden_mstatus_reg(trace):
    m, out = St(), []
    for step in trace:
        out.append(m.outputs())
        m.edge(step)
    return out


def traces(rng):
    out = []
    for _ in range(60):
        t = [{"rst": 1, "trap_m": 0, "trap_s": 0, "mret": 0, "sret": 0, "we_m": 0, "we_s": 0, "wdata": 0}]
        for _ in range(120):
            ev = rng.choice(["trap_m", "trap_s", "mret", "sret", "we_m", "we_s", None, None])
            s = {"rst": int(rng.random() < 0.01), "trap_m": 0, "trap_s": 0, "mret": 0, "sret": 0, "we_m": 0, "we_s": 0,
                 "wdata": rng.getrandbits(32)}
            if ev:
                s[ev] = 1
            out_t = s
            t.append(out_t)
        out.append(t)
    return out
