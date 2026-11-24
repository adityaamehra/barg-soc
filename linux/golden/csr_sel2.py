"""Golden model of `csr_sel2`: the CSR an instruction names, and whether the access is illegal. Combinational. Written by hand."""

SEL = {0x300: 1, 0x301: 2, 0x302: 3, 0x303: 4, 0x304: 5, 0x305: 6, 0x306: 7, 0x340: 8, 0x341: 9, 0x342: 10, 0x343: 11, 0x344: 12,
       0xB00: 13, 0xB02: 14, 0xB80: 15, 0xB82: 16, 0xC00: 17, 0xC01: 18, 0xC02: 19, 0xC80: 20, 0xC81: 21, 0xC82: 22,
       0xF11: 23, 0xF12: 24, 0xF13: 25, 0xF14: 26, 0x100: 27, 0x104: 28, 0x105: 29, 0x106: 30, 0x140: 31, 0x141: 32, 0x142: 33,
       0x143: 34, 0x144: 35, 0x180: 36, 0x7A0: 37, 0x7A1: 38, 0x7A2: 39, 0x7A3: 40, 0x320: 41, 0x3A0: 42, 0x3B0: 43}
ADDR = {v: k for k, v in SEL.items()}
COUNTER_BIT = {17: 0, 18: 1, 19: 2, 20: 0, 21: 1, 22: 2}
MISA = 0x40141105
SSTATUS_MASK = 0x000C0122
MEDELEG_MASK = 0xB3FF
MIDELEG_MASK = 0x222
M32 = 0xFFFFFFFF


def golden_csr_sel2(inst, csrop, priv, tvm, mcounteren, scounteren):
    a = inst >> 20 & 0xFFF
    sel = SEL.get(a, 0)
    op = csrop & 7
    priv &= 3
    access = op in (1, 2, 3, 4)
    write = op in (2, 3, 4)
    bad = sel == 0 or priv < (a >> 8 & 3) or (write and a >> 10 == 3) or (sel == 36 and priv == 1 and tvm & 1)
    if sel in COUNTER_BIT and priv < 3:
        bit = COUNTER_BIT[sel]
        if not (mcounteren >> bit & 1) or (priv == 0 and not (scounteren >> bit & 1)):
            bad = True
    return {"sel": sel, "illegal": int(access and bad)}


def vectors(rng):
    addrs = list(ADDR.values()) + [0x000, 0x3A0, 0x7A0, 0xB03, 0x30A, 0x320, 0xFB0, 0x5A8, 0x200, 0x181, 0xC03, 0xF15]
    out = []
    for _ in range(5000):
        a = rng.choice(addrs) if rng.random() < 0.9 else rng.getrandbits(12)
        out.append({"inst": (a << 20) | rng.getrandbits(20), "csrop": rng.randrange(8), "priv": rng.choice([0, 1, 3, 2]),
                    "tvm": rng.getrandbits(1), "mcounteren": rng.getrandbits(3), "scounteren": rng.getrandbits(3)})
    return out
