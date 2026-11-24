"""Golden model of `csr_mregs`: the machine-mode CSRs other than mstatus and the counters. Clocked. Written by hand (iss_s.py).
sel numbers: 3 medeleg, 4 mideleg, 5 mie, 6 mtvec, 7 mcounteren, 8 mscratch, 9 mepc, 10 mcause, 11 mtval, 12 mip, 28 sie, 35 sip."""
M = 0xFFFFFFFF
NAMES = ("mtvec", "mscratch", "mepc", "mcause", "mtval", "mie", "medeleg", "mideleg", "mcounteren", "mip_sw")


def golden_csr_mregs(trace):
    r, out = None, []
    for i in trace:
        out.append({k: None for k in NAMES} if r is None else dict(r))
        if i["rst"] & 1:
            r = {k: 0 for k in NAMES}
            continue
        if r is None:
            continue
        if i["trap_m"] & 1:
            r["mepc"], r["mcause"], r["mtval"] = i["epc"] & M & ~1, i["cause_val"] & M, i["tval"] & M
        elif i["we"] & 1:
            v, s = i["nval"] & M, i["sel"] & 63
            if s == 3:
                r["medeleg"] = v & 0xB3FF
            elif s == 4:
                r["mideleg"] = v & 0x222
            elif s == 5:
                r["mie"] = v & 0xAAA
            elif s == 6:
                r["mtvec"] = v & ~2 & M
            elif s == 7:
                r["mcounteren"] = v & 7
            elif s == 8:
                r["mscratch"] = v
            elif s == 9:
                r["mepc"] = v & ~1 & M
            elif s == 10:
                r["mcause"] = v
            elif s == 11:
                r["mtval"] = v
            elif s == 12:
                r["mip_sw"] = (r["mip_sw"] & 0x200) | (v & 0x22)
            elif s == 28:
                r["mie"] = (r["mie"] & ~r["mideleg"]) | (v & r["mideleg"] & 0x222)
            elif s == 35:
                r["mip_sw"] = (r["mip_sw"] & ~(r["mideleg"] & 2)) | (v & r["mideleg"] & 2)
    return out


def traces(rng):
    out = []
    for _ in range(50):
        t = [{"rst": 1, "sel": 0, "we": 0, "nval": 0, "trap_m": 0, "epc": 0, "cause_val": 0, "tval": 0}]
        for _ in range(120):
            tm = int(rng.random() < 0.1)
            t.append({"rst": int(rng.random() < 0.01), "sel": rng.choice([3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 28, 35, 1, 29, 0, 36]),
                      "we": int(not tm and rng.random() < 0.6), "nval": rng.getrandbits(32), "trap_m": tm, "epc": rng.getrandbits(32),
                      "cause_val": rng.getrandbits(32), "tval": rng.getrandbits(32)})
        out.append(t)
    return out
