"""Golden model of `line_addrs8`. Combinational. Written by hand."""


def golden_line_addrs8(a):
    base = a & 0xFFFFFFE0
    y = 0
    for j in range(8):
        y |= ((base + 4 * j) & 0xFFFFFFFF) << (32 * j)
    return {"y": y}


def vectors(rng):
    return [{"a": rng.getrandbits(32)} for _ in range(500)]
