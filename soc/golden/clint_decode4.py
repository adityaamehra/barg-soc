"""Golden model of the four-hart CLINT register decoder (block `clint_decode4`). Combinational. Written by hand.

Word w = addr bits 15:2. kind 1 (msip) for w = 0..3 (hart = w); kind 2 / 3 (mtimecmp low / high) for w = 0x1000 + 2h / + 1 (hart h =
0..3: offsets 0x4000 + 8h and 0x4004 + 8h); kind 4 / 5 (mtime low / high) for w = 0x2FFE / 0x2FFF (offsets 0xBFF8, 0xBFFC; hart 0).
Everything else: kind 0, hart 0. QEMU virt's layout for four harts."""


def golden_clint_decode4(addr):
    w = (addr >> 2) & 0x3FFF
    kind, hart = 0, 0
    if w < 4:
        kind, hart = 1, w
    elif 0x1000 <= w < 0x1008:
        kind, hart = 2 + (w & 1), (w - 0x1000) >> 1
    elif w == 0x2FFE:
        kind = 4
    elif w == 0x2FFF:
        kind = 5
    return {"kind": kind, "hart": hart}


def vectors(rng):
    words = list(range(8)) + list(range(0x0FFE, 0x1010)) + [0x2FFD, 0x2FFE, 0x2FFF, 0x3000, 0x3FFF]
    return [{"addr": (rng.getrandbits(16) << 16) | (w << 2) | rng.getrandbits(2)} for w in words for _ in range(3)] + \
           [{"addr": rng.getrandbits(32)} for _ in range(500)]
