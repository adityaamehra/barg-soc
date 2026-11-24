"""Golden model of `zeros`: constant zeros. Combinational. Written by hand."""


def golden_zeros():
    return {"z1": 0, "z4": 0, "z32": 0}


def vectors(rng):
    return [{} for _ in range(4)]
