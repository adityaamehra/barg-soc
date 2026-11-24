"""Golden model of `pack16w`: sixteen 24-bit word addresses as one 384-bit bus (a0 in bits 23:0, a15 in bits 383:360). Written by hand."""


def golden_pack16w(**a):
    v = 0
    for k in range(16):
        v |= (a[f"a{k}"] & 0xFFFFFF) << (24 * k)
    return {"bus384": v}


def vectors(rng):
    return [{f"a{k}": rng.getrandbits(24) for k in range(16)} for _ in range(1500)]
