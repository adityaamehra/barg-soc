"""Golden model of `wfi_wake`: hold the pipeline at a WFI instruction until an enabled interrupt is pending. Written by hand."""


def golden_wfi_wake(inst, msip, mtip, meip, mip_sw, mie):
    pend = (mip_sw & 0xFFF) | ((msip & 1) << 3) | ((mtip & 1) << 7) | ((meip & 1) << 11)
    return {"hold": int(inst == 0x10500073 and (pend & mie & 0xFFF) == 0)}


def vectors(rng):
    out = []
    for _ in range(3000):
        inst = 0x10500073 if rng.random() < 0.6 else rng.choice([0x00000013, 0x10500073 ^ (1 << rng.randrange(32)), rng.getrandbits(32)])
        mie = rng.getrandbits(12) if rng.random() < 0.7 else 0
        sw = rng.getrandbits(12) if rng.random() < 0.3 else 0
        out.append({"inst": inst, "msip": rng.getrandbits(1), "mtip": rng.getrandbits(1), "meip": rng.getrandbits(1), "mip_sw": sw, "mie": mie})
    return out
