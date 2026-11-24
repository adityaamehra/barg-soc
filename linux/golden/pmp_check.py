"""Golden model of `pmp_check`: whether the physical memory protection (16 entries, OFF/TOR/NA4/NAPOT, lock bit) refuses an access. Combinational. Written by hand."""
M32 = 0xFFFFFFFF


def golden_pmp_check(pa, kind, priv, en, cfg_all, addr_all):
    if not en & 1:
        return {"deny": 0}
    w = (pa & M32) >> 2
    priv &= 3
    kind &= 3
    for i in range(16):
        c = cfg_all >> (8 * i) & 0xFF
        a = addr_all >> (32 * i) & M32
        prev = (addr_all >> (32 * (i - 1)) & M32) if i else 0
        mode = c >> 3 & 3
        if mode == 1:
            m = prev <= w < a
        elif mode == 2:
            m = w == a
        elif mode == 3:
            mm = (a ^ ((a + 1) & M32)) & M32
            m = (w & ~mm & M32) == (a & ~mm & M32)
        else:
            m = False
        if m:
            allow = bool(c >> 2 & 1) if kind == 0 else bool(c & 1) if kind == 1 else bool(c >> 1 & 1)
            return {"deny": int((priv != 3 or bool(c >> 7 & 1)) and not allow)}
    return {"deny": int(priv != 3)}


def vectors(rng):
    out = []
    for _ in range(6000):
        cfg = addr = 0
        n = rng.randrange(1, 6) if rng.random() < 0.8 else 16
        base = rng.getrandbits(20) << 8
        for i in range(16):
            if i < n:
                mode = rng.choice([0, 1, 2, 3, 3, 1])
                c = (rng.getrandbits(3)) | (mode << 3) | (rng.getrandbits(1) << 7 if rng.random() < 0.3 else 0)
                if mode == 3:
                    a = ((base >> 2) | ((1 << rng.randrange(0, 12)) - 1)) & M32
                elif mode == 1:
                    a = ((base >> 2) + rng.randrange(0, 4096)) & M32
                else:
                    a = ((base >> 2) + rng.randrange(0, 64)) & M32
            else:
                c, a = 0, rng.getrandbits(32) if rng.random() < 0.2 else 0
            cfg |= c << (8 * i)
            addr |= a << (32 * i)
        pa = ((base + rng.randrange(0, 1 << 14)) if rng.random() < 0.85 else rng.getrandbits(32)) & M32
        out.append({"pa": pa, "kind": rng.randrange(4), "priv": rng.choice([0, 1, 3, 3, 1, 0]), "en": int(rng.random() < 0.9), "cfg_all": cfg, "addr_all": addr})
    return out
