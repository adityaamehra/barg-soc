"""Golden model of `satp_split`. Combinational. Written by hand."""


def golden_satp_split(satp):
    return {"mode": satp >> 31 & 1, "ppn": satp & 0x3FFFFF}


def vectors(rng):
    return [{"satp": rng.getrandbits(32)} for _ in range(1000)]
