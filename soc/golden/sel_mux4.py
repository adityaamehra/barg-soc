"""Golden model of `sel_mux4`: OR of the inputs whose selects are 1. Combinational. Written by hand."""


def golden_sel_mux4(sel0, sel1, sel2, sel3, d0, d1, d2, d3):
    y = 0
    for s, d in ((sel0, d0), (sel1, d1), (sel2, d2), (sel3, d3)):
        if s & 1:
            y |= d & 0xFFFFFFFF
    return {"y": y}


def vectors(rng):
    out = []
    for _ in range(600):
        v = {f"sel{k}": int(rng.random() < 0.3) for k in range(4)}
        v.update({f"d{k}": rng.getrandbits(32) for k in range(4)})
        out.append(v)
    return out
