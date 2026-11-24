"""Golden model of `mip_merge`: the mip register as read. Combinational. Written by hand."""


def golden_mip_merge(mip_sw, meip, mtip, msip):
    return {"mip": (mip_sw & 0x222) | (meip & 1) << 11 | (mtip & 1) << 7 | (msip & 1) << 3}


def vectors(rng):
    return [{"mip_sw": rng.getrandbits(12), "meip": rng.getrandbits(1), "mtip": rng.getrandbits(1), "msip": rng.getrandbits(1)}
            for _ in range(1000)]
