"""Golden model of `pa_mux`: the physical address. Combinational. Written by hand."""


def golden_pa_mux(xlate, va, ppa):
    return {"pa": ((ppa & 0xFFFFF) << 12 | (va & 0xFFF)) if xlate & 1 else va & 0xFFFFFFFF}


def vectors(rng):
    return [{"xlate": rng.getrandbits(1), "va": rng.getrandbits(32), "ppa": rng.getrandbits(20)} for _ in range(2000)]
