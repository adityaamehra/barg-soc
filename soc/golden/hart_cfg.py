"""Golden model of the hart configuration (block `hart_cfg`). Combinational. Written by hand."""


def golden_hart_cfg(meip):
    return {"meip0": meip & 1, "meip1": 0, "meip2": 0, "meip3": 0, "hartid0": 0, "hartid1": 1, "hartid2": 2, "hartid3": 3}


def vectors(rng):
    return [{"meip": 0}, {"meip": 1}] * 4
