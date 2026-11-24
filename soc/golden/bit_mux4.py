"""Golden model of `bit_mux4`: OR of (select AND data). Combinational. Written by hand."""


def golden_bit_mux4(sel0, sel1, sel2, sel3, d0, d1, d2, d3):
    return {"y": ((sel0 & d0) | (sel1 & d1) | (sel2 & d2) | (sel3 & d3)) & 1}


def vectors(rng):
    return [{**{f"sel{k}": rng.getrandbits(1) for k in range(4)}, **{f"d{k}": rng.getrandbits(1) for k in range(4)}} for _ in range(300)]
