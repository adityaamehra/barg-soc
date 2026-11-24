"""Golden model of `mip_merge_s`: the mip register as read, with a supervisor external interrupt input (bit 9 = mip_sw bit 9 OR seip). Combinational. Written by hand."""


def golden_mip_merge_s(mip_sw, meip, mtip, msip, seip):
    return {"mip": (mip_sw & 0x22) | ((mip_sw >> 9 & 1) | (seip & 1)) << 9 | (meip & 1) << 11 | (mtip & 1) << 7 | (msip & 1) << 3}


def vectors(rng):
    return [{"mip_sw": rng.getrandbits(12), "meip": rng.getrandbits(1), "mtip": rng.getrandbits(1), "msip": rng.getrandbits(1), "seip": rng.getrandbits(1)} for _ in range(1500)]
