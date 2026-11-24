"""Golden model of `fp_stmux`. Combinational. Written by hand."""


def golden_fp_stmux(from_core, fdata, is_fst, dwsel):
    if not is_fst:
        return {"y": from_core}
    return {"y": fdata >> 32 if dwsel == 2 else fdata & 0xFFFFFFFF}


def vectors(rng):
    return [{"from_core": rng.getrandbits(32), "fdata": rng.getrandbits(64), "is_fst": rng.getrandbits(1), "dwsel": rng.getrandbits(2)} for _ in range(1000)]
