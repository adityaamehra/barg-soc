"""Golden model of `pmp_k`: constants and the kind code of a data access for the PMP checks. Combinational. Written by hand."""


def golden_pmp_k(store):
    return {"kind_f": 0, "kind_d": 2 if store & 1 else 1, "kind_l": 1, "priv_s": 1, "one": 1}


def vectors(rng):
    return [{"store": rng.getrandbits(1)} for _ in range(50)]
