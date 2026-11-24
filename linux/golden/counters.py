"""Golden model of `counters`: mcycle and minstret, 64 bits each, with writes from a CSR instruction. Clocked. Written by hand."""
M64 = (1 << 64) - 1
WRITE = {13: ("c", 0), 15: ("c", 1), 14: ("i", 0), 16: ("i", 1)}


def golden_counters(trace):
    c, out = None, []
    for i in trace:
        out.append({"mcycle": None, "minstret": None} if c is None else {"mcycle": c[0], "minstret": c[1]})
        if i["rst"] & 1:
            c = [0, 0]
            continue
        if c is None:
            continue
        mc, mi = c
        w = WRITE.get(i["sel"] & 63) if i["we"] & 1 else None
        # the written counter takes the value and does not count on this edge; the other counter counts as usual
        if w is None or w[0] != "c":
            mc = (mc + 1) & M64
        if w is None or w[0] != "i":
            mi = (mi + (i["retire"] & 1)) & M64
        if w is not None:
            which, high = w
            v = i["nval"] & 0xFFFFFFFF
            cur = mc if which == "c" else mi
            cur = (cur & 0xFFFFFFFF) | (v << 32) if high else (cur & ~0xFFFFFFFF & M64) | v
            if which == "c":
                mc = cur
            else:
                mi = cur
        c = [mc, mi]
    return out


def traces(rng):
    out = []
    for _ in range(10):
        t = [{"rst": 1, "retire": 0, "we": 0, "sel": 0, "nval": 0}]
        for _ in range(300):
            we = int(rng.random() < 0.1)
            t.append({"rst": int(rng.random() < 0.005), "retire": rng.getrandbits(1), "we": we,
                      "sel": rng.choice([13, 14, 15, 16, 17, 1, 0]), "nval": rng.getrandbits(32)})
        out.append(t)
    return out
