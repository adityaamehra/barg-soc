"""Golden model of `word_addr`: bits 23:2 of a byte address. Combinational. Written by hand."""


def golden_word_addr(addr):
    return {"word": (addr >> 2) & 0x3FFFFF}


def vectors(rng):
    return [{"addr": rng.getrandbits(32)} for _ in range(2000)]
