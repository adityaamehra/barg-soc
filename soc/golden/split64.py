"""Golden model of `split64`: a 64-bit bus as two 32-bit words. Combinational. Written by hand."""


def golden_split64(y):
    return {"lo": y & 0xFFFFFFFF, "hi": (y >> 32) & 0xFFFFFFFF}


def vectors(rng):
    return [{"y": rng.getrandbits(64)} for _ in range(400)]
