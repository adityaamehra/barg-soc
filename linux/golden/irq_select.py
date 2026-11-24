"""Golden model of `irq_select`: which interrupt is taken, with delegation to S-mode. Combinational. Written by hand.
mip bits: 1 SSI, 3 MSI, 5 STI, 7 MTI, 9 SEI, 11 MEI. Priority MEI, MSI, MTI, SEI, SSI, STI."""


def golden_irq_select(mip, mie, mideleg, priv, mstatus_mie, mstatus_sie):
    p = mip & mie & 0xAAA
    priv &= 3
    for cause in (11, 3, 7, 9, 1, 5):
        if not p >> cause & 1:
            continue
        if mideleg >> cause & 1:
            if priv < 1 or (priv == 1 and mstatus_sie & 1):
                return {"pending": 1, "cause": cause}
        elif priv < 3 or mstatus_mie & 1:
            return {"pending": 1, "cause": cause}
    return {"pending": 0, "cause": 0}


def vectors(rng):
    out = []
    for _ in range(5000):
        out.append({"mip": rng.getrandbits(12) & (0xAAA if rng.random() < 0.8 else 0xFFF), "mie": rng.getrandbits(12),
                    "mideleg": rng.choice([0, 0x222, rng.getrandbits(12)]), "priv": rng.choice([0, 1, 3, 2]),
                    "mstatus_mie": rng.getrandbits(1), "mstatus_sie": rng.getrandbits(1)})
    return out
