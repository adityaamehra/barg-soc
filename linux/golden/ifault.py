"""Golden model of `ifault`: a fetch that faulted enters the pipeline as a reserved word. Combinational. Written by hand.
The word: opcode 0001011 (custom-0), funct3 001 for a page fault or 010 for an access fault, bit 20 set when the second half of the
instruction (the next word) faulted; every other bit 0."""


def golden_ifault(inst, is16, pc, word_lo, xlate, lo_pf, lo_af, hi_pf, hi_af):
    x = bool(xlate & 1)
    need_hi = bool(pc >> 1 & 1) and (word_lo >> 16 & 3) == 3
    if x and (lo_pf & 1 or lo_af & 1):
        return {"inst_out": 0x0B | (2 if lo_af & 1 and not lo_pf & 1 else 1) << 12, "is16_out": 0}
    if x and need_hi and (hi_pf & 1 or hi_af & 1):
        return {"inst_out": 0x0B | (2 if hi_af & 1 and not hi_pf & 1 else 1) << 12 | 1 << 20, "is16_out": 0}
    return {"inst_out": inst & 0xFFFFFFFF, "is16_out": is16 & 1}


def vectors(rng):
    out = []
    for _ in range(4000):
        out.append({"inst": rng.getrandbits(32), "is16": rng.getrandbits(1), "pc": rng.getrandbits(32) & ~1,
                    "word_lo": rng.getrandbits(32) | (0x30000 if rng.random() < 0.5 else 0), "xlate": int(rng.random() < 0.8),
                    "lo_pf": int(rng.random() < 0.2), "lo_af": int(rng.random() < 0.1), "hi_pf": int(rng.random() < 0.3),
                    "hi_af": int(rng.random() < 0.1)})
    return out
