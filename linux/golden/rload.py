"""Golden model of `rload`: the value a load gets from the RAM's word (what the stage-4 data memory did inside its own read).
memtype codes: 000 byte (signed), 001 half (signed), 010 word, 011 byte unsigned, 100 half unsigned, 101 no access (0), 110/111 as word.
The byte is picked by addr bits 1:0; the half-word by addr bit 1. Written by hand."""


def golden_rload(word, memtype, addr):
    t, a = memtype & 7, addr & 3
    w = word & 0xFFFFFFFF
    if t in (0, 3):
        v, sign = (w >> 8 * a) & 0xFF, t == 0
        return {"rdata": (v - 0x100 if sign and v & 0x80 else v) & 0xFFFFFFFF}
    if t in (1, 4):
        v, sign = (w >> 16 * (a >> 1)) & 0xFFFF, t == 1
        return {"rdata": (v - 0x10000 if sign and v & 0x8000 else v) & 0xFFFFFFFF}
    if t == 5:
        return {"rdata": 0}
    return {"rdata": w}


def vectors(rng):
    return [{"word": rng.getrandbits(32), "memtype": m, "addr": a} for m in range(8) for a in range(4) for _ in range(40)]
