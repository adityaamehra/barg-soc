"""Golden model of `dfault_gate`: a translation fault counts only for an instruction that accesses memory, and only while data accesses are translated. Combinational. Written by hand."""


def golden_dfault_gate(access, xlate, pf, af):
    return {"pf_o": pf & access & xlate & 1, "af_o": af & access & xlate & 1}


def vectors(rng):
    return [{"access": rng.getrandbits(1), "xlate": rng.getrandbits(1), "pf": rng.getrandbits(1), "af": rng.getrandbits(1)} for _ in range(600)]
