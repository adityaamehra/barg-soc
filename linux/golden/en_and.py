"""Golden model of `en_and`: the core's clock enable. Combinational. Written by hand."""


def golden_en_and(run, stall):
    return {"en": int(bool(run & 1) and not stall & 1)}


def vectors(rng):
    return [{"run": a, "stall": b} for a in range(2) for b in range(2)] * 10
