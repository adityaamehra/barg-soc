"""Golden model of `csr_hw`: the hard-wired CSR addresses (mstatush, mhpmevent3-31, mhpmcounter3-31 and their high halves) get number 44 after the decoder."""


def _hw(a):
    return a in (0x310, 0x30A, 0x31A, 0x10A) or 0x323 <= a <= 0x33F or 0xB03 <= a <= 0xB1F or 0xB83 <= a <= 0xB9F or 0xC03 <= a <= 0xC1F or 0xC83 <= a <= 0xC9F


def golden_csr_hw(inst, csrop, priv, sel_in, ill_in):
    a = inst >> 20 & 0xFFF
    if (sel_in & 63) == 0 and (0x3A1 <= a <= 0x3A3 or 0x3B1 <= a <= 0x3BF):
        access = (csrop & 7) in (1, 2, 3, 4)
        return {"sel_out": 42 if a <= 0x3A3 else 43, "ill_out": int(access and (priv & 3) != 3)}
    if (sel_in & 63) == 0 and _hw(a):
        op = csrop & 7
        access = op in (1, 2, 3, 4)
        write = op in (2, 3, 4)
        return {"sel_out": 44, "ill_out": int((access and (priv & 3) != 3) or (write and (a >> 10) == 3))}
    return {"sel_out": sel_in & 63, "ill_out": ill_in & 1}


def vectors(rng):
    addrs = [0x3A1, 0x3A3, 0x3A4, 0x3B1, 0x3BF, 0x3C0, 0x3A0, 0x3B0, 0xC03, 0xC1F, 0xC20, 0xC83, 0xC9F, 0xCA0, 0xC02, 0xC82, 0x10A, 0x109, 0x10B, 0x30A, 0x31A, 0x30B, 0x319, 0x310, 0x323, 0x33F, 0x340, 0x322, 0xB03, 0xB1F, 0xB20, 0xB02, 0xB83, 0xB9F, 0xBA0, 0xB82, 0x300, 0x000, 0xFFF, 0x324, 0xB10, 0xB90, 0x330]
    out = []
    for _ in range(4000):
        a = rng.choice(addrs) if rng.random() < 0.85 else rng.getrandbits(12)
        out.append({"inst": (a << 20) | rng.getrandbits(20), "csrop": rng.randrange(8), "priv": rng.randrange(4),
                    "sel_in": 0 if rng.random() < 0.6 else rng.randrange(64), "ill_in": rng.getrandbits(1)})
    return out
