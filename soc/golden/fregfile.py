"""Golden model of `fregfile`: 32 x 64-bit register file with two independent write halves. Clocked. Written by hand. Registers are unknown (None)
until written, so reads of never-written registers are not compared."""


def golden_fregfile(trace):
    regs = [[None, None] for _ in range(32)]          # [lo, hi]
    out = []
    for i in trace:
        row = {}
        for k, a in (("rdata1", i["ra1"]), ("rdata2", i["ra2"]), ("rdata3", i["ra3"])):
            lo, hi = regs[a]
            row[k] = None if lo is None or hi is None else hi << 32 | lo
        out.append(row)
        if i["we_lo"]:
            regs[i["waddr"]][0] = i["wdata_lo"]
        if i["we_hi"]:
            regs[i["waddr"]][1] = i["wdata_hi"]
    return out


def traces(rng):
    out = []
    for _ in range(30):
        t = []
        for _ in range(200):
            t.append({"we_lo": int(rng.random() < 0.5), "we_hi": int(rng.random() < 0.5), "waddr": rng.randrange(8) if rng.random() < 0.8 else rng.randrange(32),
                      "wdata_lo": rng.getrandbits(32), "wdata_hi": rng.getrandbits(32), "ra1": rng.randrange(8), "ra2": rng.randrange(8), "ra3": rng.randrange(32)})
        out.append(t)
    return out
