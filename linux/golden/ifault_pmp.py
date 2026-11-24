"""Golden model of `ifault_pmp`: ifault with the physical memory protection's refusal of the fetch (pmp_lo, pmp_hi), which counts whether or not fetches are translated. Combinational."""


def golden_ifault_pmp(inst, is16, pc, word_lo, xlate, lo_pf, lo_af, hi_pf, hi_af, pmp_lo, pmp_hi):
    x = bool(xlate & 1)
    need_hi = bool(pc >> 1 & 1) and (word_lo >> 16 & 3) == 3
    if x and lo_pf & 1:
        return {"inst_out": 0x0B | 1 << 12, "is16_out": 0}
    if (x and lo_af & 1) or pmp_lo & 1:
        return {"inst_out": 0x0B | 2 << 12, "is16_out": 0}
    if x and need_hi and hi_pf & 1:
        return {"inst_out": 0x0B | 1 << 12 | 1 << 20, "is16_out": 0}
    if need_hi and ((x and hi_af & 1) or pmp_hi & 1):
        return {"inst_out": 0x0B | 2 << 12 | 1 << 20, "is16_out": 0}
    return {"inst_out": inst & 0xFFFFFFFF, "is16_out": is16 & 1}


def vectors(rng):
    out = []
    for _ in range(5000):
        out.append({"inst": rng.getrandbits(32), "is16": rng.getrandbits(1), "pc": rng.getrandbits(32) & ~1,
                    "word_lo": rng.getrandbits(32) | (0x30000 if rng.random() < 0.5 else 0), "xlate": int(rng.random() < 0.7),
                    "lo_pf": int(rng.random() < 0.2), "lo_af": int(rng.random() < 0.1), "hi_pf": int(rng.random() < 0.3),
                    "hi_af": int(rng.random() < 0.1), "pmp_lo": int(rng.random() < 0.15), "pmp_hi": int(rng.random() < 0.15)})
    return out
