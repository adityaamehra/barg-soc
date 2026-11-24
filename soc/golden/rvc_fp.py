"""Golden model of `rvc_fp`: the eight compressed FP loads and stores expanded to 32 bits. Combinational. Written by hand from the C extension."""


def expand(h):
    q, f3 = h & 3, h >> 13 & 7
    if q == 0 and f3 in (1, 3, 5, 7):
        rs1, r2 = 8 + (h >> 7 & 7), 8 + (h >> 2 & 7)
        if f3 in (1, 5):
            uimm = (h >> 10 & 7) << 3 | (h >> 5 & 3) << 6
        else:
            uimm = (h >> 10 & 7) << 3 | (h >> 6 & 1) << 2 | (h >> 5 & 1) << 6
        funct3 = 3 if f3 in (1, 5) else 2
        if f3 in (1, 3):
            return uimm << 20 | rs1 << 15 | funct3 << 12 | r2 << 7 | 0x07
        return (uimm >> 5) << 25 | r2 << 20 | rs1 << 15 | funct3 << 12 | (uimm & 31) << 7 | 0x27
    if q == 2 and f3 in (1, 3, 5, 7):
        if f3 in (1, 3):
            rd = h >> 7 & 31
            if f3 == 1:
                uimm = (h >> 12 & 1) << 5 | (h >> 5 & 3) << 3 | (h >> 2 & 7) << 6
            else:
                uimm = (h >> 12 & 1) << 5 | (h >> 4 & 7) << 2 | (h >> 2 & 3) << 6
            return uimm << 20 | 2 << 15 | (3 if f3 == 1 else 2) << 12 | rd << 7 | 0x07
        rs2 = h >> 2 & 31
        if f3 == 5:
            uimm = (h >> 10 & 7) << 3 | (h >> 7 & 7) << 6
        else:
            uimm = (h >> 9 & 15) << 2 | (h >> 7 & 3) << 6
        return (uimm >> 5) << 25 | rs2 << 20 | 2 << 15 | (3 if f3 == 5 else 2) << 12 | (uimm & 31) << 7 | 0x27
    return None


def golden_rvc_fp(inst, word_in):
    e = expand(inst & 0xFFFF) if inst & 3 != 3 else None
    return {"word_out": word_in if e is None else e}


def vectors(rng):
    v = []
    for _ in range(3000):
        inst = rng.getrandbits(32)
        if rng.random() < 0.7:
            inst = (inst & ~0xE003) | rng.choice((0, 2)) | rng.choice((1, 3, 5, 7)) << 13
        v.append({"inst": inst, "word_in": rng.getrandbits(32)})
    return v
