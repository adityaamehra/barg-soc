"""Golden model of `pack4`: four 22-bit word addresses as one 88-bit bus (a0 in bits 21:0). Combinational. Written by hand."""


def golden_pack4(a0, a1, a2, a3):
    return {"bus88": (a0 & 0x3FFFFF) | (a1 & 0x3FFFFF) << 22 | (a2 & 0x3FFFFF) << 44 | (a3 & 0x3FFFFF) << 66}


def vectors(rng):
    return [{"a0": rng.getrandbits(22), "a1": rng.getrandbits(22), "a2": rng.getrandbits(22), "a3": rng.getrandbits(22)} for _ in range(2000)]
