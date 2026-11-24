"""Golden model of `status_we`. Combinational. Written by hand."""


def golden_status_we(csr_we, sel):
    w = bool(csr_we & 1)
    return {"we_m": int(w and sel & 63 == 1), "we_s": int(w and sel & 63 == 27)}


def vectors(rng):
    return [{"csr_we": w, "sel": s} for w in range(2) for s in range(64)] * 3
