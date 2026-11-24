"""Golden model of `pmp_regs16`: the sixteen PMP entry configurations and addresses with their CSR access rules (lock bit, reserved R/W combination, locked TOR above).
Clocked: held state cfg[16], addr[16]; None before the first reset."""
M32 = 0xFFFFFFFF


def _out(cfg, addr, i):
    a = i["inst"] >> 20 & 0xFFF
    if 0x3A0 <= a <= 0x3A3:
        n = a - 0x3A0
        rd = sum(cfg[4 * n + j] << (8 * j) for j in range(4))
    elif 0x3B0 <= a <= 0x3BF:
        rd = addr[a - 0x3B0]
    else:
        rd = 0
    return {"rdata": rd, "cfg_all": sum(cfg[k] << (8 * k) for k in range(16)), "addr_all": sum(addr[k] << (32 * k) for k in range(16))}


def golden_pmp_regs16(trace):
    st = None
    out = []
    for i in trace:
        out.append({"rdata": None, "cfg_all": None, "addr_all": None} if st is None else _out(st[0], st[1], i))
        if i["rst"] & 1:
            st = ([0] * 16, [0] * 16)
        elif st is not None:
            cfg, addr = list(st[0]), list(st[1])
            a = i["inst"] >> 20 & 0xFFF
            if (i["we"] & 1) and (i["sel"] & 63) in (42, 43, 45):
                if 0x3A0 <= a <= 0x3A3:
                    n = a - 0x3A0
                    for j in range(4):
                        e = 4 * n + j
                        b = i["nval"] >> (8 * j) & 0xFF
                        if cfg[e] >> 7 & 1:
                            continue
                        if not b & 1 and b >> 1 & 1:
                            continue
                        cfg[e] = b & 0x9F
                elif 0x3B0 <= a <= 0x3BF:
                    n = a - 0x3B0
                    locked = cfg[n] >> 7 & 1
                    tor_above = n < 15 and (cfg[n + 1] >> 7 & 1) and (cfg[n + 1] >> 3 & 3) == 1
                    if not locked and not tor_above:
                        addr[n] = i["nval"] & M32
            st = (cfg, addr)
    return out


def traces(rng):
    out = []
    for _ in range(40):
        t = [{"rst": 1, "we": 0, "inst": 0, "sel": 0, "nval": 0}]
        for _ in range(300):
            kind = rng.random()
            if kind < 0.4:
                a = 0x3A0 + rng.randrange(4)
            elif kind < 0.85:
                a = 0x3B0 + rng.randrange(16)
            else:
                a = rng.choice([0x3A4, 0x3AF, 0x3C0, 0x300, 0x000, 0xFFF])
            nval = rng.getrandbits(32)
            if a < 0x3A4 and rng.random() < 0.7:   # configurations: few locks, mostly legal
                nval &= 0x7F7F7F7F if rng.random() < 0.8 else M32
            t.append({"rst": int(rng.random() < 0.004), "we": int(rng.random() < 0.8), "inst": (a << 20) | rng.getrandbits(20),
                      "sel": rng.choice([42, 43, 45, 45, 45, 0, 7]), "nval": nval})
        out.append(t)
    return out
