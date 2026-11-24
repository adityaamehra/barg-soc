"""Golden model of `wlane`: a store's bytes placed on their lanes of a 32-bit word, with byte enables. Combinational. Written by hand.
memtype: 0 byte, 1 half, 2 word, 3 byte (unsigned), 4 half (unsigned), 5 no access, 6 and 7 as a word."""


def golden_wlane(memtype, addr, wdata):
    t, a = memtype & 7, addr & 3
    if t in (0, 3):
        return {"be": 1 << a, "data": ((wdata & 0xFF) << 8 * a) & 0xFFFFFFFF}
    if t in (1, 4):
        h = a >> 1
        return {"be": 3 << 2 * h, "data": ((wdata & 0xFFFF) << 16 * h) & 0xFFFFFFFF}
    if t == 5:
        return {"be": 0, "data": 0}
    return {"be": 15, "data": wdata & 0xFFFFFFFF}


def vectors(rng):
    return [{"memtype": rng.randrange(8), "addr": rng.getrandbits(32), "wdata": rng.getrandbits(32)} for _ in range(3000)]
