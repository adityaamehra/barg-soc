"""Golden model of `csr_sregs`: the supervisor CSRs. Clocked. Written by hand (iss_s.py).
sel numbers: 29 stvec, 30 scounteren, 31 sscratch, 32 sepc, 33 scause, 34 stval, 36 satp."""
M = 0xFFFFFFFF
NAMES = ("stvec", "sscratch", "sepc", "scause", "stval", "satp", "scounteren")


def golden_csr_sregs(trace):
    r, out = None, []
    for i in trace:
        out.append({k: None for k in NAMES} if r is None else dict(r))
        if i["rst"] & 1:
            r = {k: 0 for k in NAMES}
            continue
        if r is None:
            continue
        if i["trap_s"] & 1:
            r["sepc"], r["scause"], r["stval"] = i["epc"] & M & ~1, i["cause_val"] & M, i["tval"] & M
        elif i["we"] & 1:
            v, s = i["nval"] & M, i["sel"] & 63
            if s == 29:
                r["stvec"] = v & ~2 & M
            elif s == 30:
                r["scounteren"] = v & 7
            elif s == 31:
                r["sscratch"] = v
            elif s == 32:
                r["sepc"] = v & ~1 & M
            elif s == 33:
                r["scause"] = v
            elif s == 34:
                r["stval"] = v
            elif s == 36:
                r["satp"] = v & 0x803FFFFF
    return out


def traces(rng):
    out = []
    for _ in range(50):
        t = [{"rst": 1, "sel": 0, "we": 0, "nval": 0, "trap_s": 0, "epc": 0, "cause_val": 0, "tval": 0}]
        for _ in range(120):
            ts = int(rng.random() < 0.1)
            t.append({"rst": int(rng.random() < 0.01), "sel": rng.choice([29, 30, 31, 32, 33, 34, 36, 1, 5, 0, 35]),
                      "we": int(not ts and rng.random() < 0.6), "nval": rng.getrandbits(32), "trap_s": ts, "epc": rng.getrandbits(32),
                      "cause_val": rng.getrandbits(32), "tval": rng.getrandbits(32)})
        out.append(t)
    return out
