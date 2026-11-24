"""Golden model of `cat64`: two 32-bit words as one 64-bit bus. Combinational. Written by hand."""


def golden_cat64(a, b):
    return {"y": (a & 0xFFFFFFFF) | ((b & 0xFFFFFFFF) << 32)}


def vectors(rng):
    return [{"a": rng.getrandbits(32), "b": rng.getrandbits(32)} for _ in range(400)]
