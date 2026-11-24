"""Golden model of `split2`: a 2-bit bus as two bits. Combinational. Written by hand."""


def golden_split2(y):
    return {"b0": y & 1, "b1": (y >> 1) & 1}


def vectors(rng):
    return [{"y": rng.getrandbits(2)} for _ in range(40)]
