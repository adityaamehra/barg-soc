"""Golden model of `fencei_gate`: a retiring fence.i. Combinational. Written by hand."""


def golden_fencei_gate(valid, csrop, trap_m, trap_s):
    return {"fence_i": int((valid & 1) and (csrop & 7) == 7 and not (trap_m & 1) and not (trap_s & 1))}


def vectors(rng):
    return [{"valid": rng.getrandbits(1), "csrop": rng.choice([7, 7, rng.getrandbits(3)]), "trap_m": rng.getrandbits(1), "trap_s": rng.getrandbits(1)} for _ in range(300)]
