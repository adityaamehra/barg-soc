"""Golden model of `pmp_regs`: pmpcfg0 and pmpaddr0 as held registers written by CSR instructions. Clocked. Written by hand."""
M32 = 0xFFFFFFFF


def golden_pmp_regs(trace):
    r, out = None, []
    for i in trace:
        out.append({"pmpcfg0": None, "pmpaddr0": None} if r is None else {"pmpcfg0": r[0], "pmpaddr0": r[1]})
        if i["rst"] & 1:
            r = [0, 0]
            continue
        if r is None:
            continue
        if i["we"] & 1:
            if i["sel"] & 63 == 42:
                r[0] = i["nval"] & M32
            elif i["sel"] & 63 == 43:
                r[1] = i["nval"] & M32
    return out


def traces(rng):
    out = []
    for _ in range(20):
        t = [{"rst": 1, "we": 0, "sel": 0, "nval": 0}]
        for _ in range(120):
            t.append({"rst": int(rng.random() < 0.01), "we": int(rng.random() < 0.5),
                      "sel": rng.choice([42, 43, 13, 0, 36]), "nval": rng.getrandbits(32)})
        out.append(t)
    return out
