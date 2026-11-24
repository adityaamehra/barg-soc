"""Golden model of `pack16`: sixteen 22-bit word addresses as one 352-bit bus (a0 in bits 21:0, a15 in bits 351:330). Written by hand."""


def golden_pack16(**a):
    v = 0
    for k in range(16):
        v |= (a[f"a{k}"] & 0x3FFFFF) << (22 * k)
    return {"bus352": v}


def vectors(rng):
    return [{f"a{k}": rng.getrandbits(22) for k in range(16)} for _ in range(1500)]
