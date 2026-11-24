"""Golden model of `word_addr24`: bits 25:2 of a byte address (the word address in a 64 MB RAM). Combinational. Written by hand."""


def golden_word_addr24(addr):
    return {"word": (addr >> 2) & 0xFFFFFF}


def vectors(rng):
    return [{"addr": rng.getrandbits(32)} for _ in range(2000)]
