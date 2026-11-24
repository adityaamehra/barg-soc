"""Golden model of `unpack4`: a 128-bit bus of four 32-bit words (word 0 in bits 31:0) split into the four words. Written by hand."""


def golden_unpack4(bus128):
    return {f"w{k}": (bus128 >> 32 * k) & 0xFFFFFFFF for k in range(4)}


def vectors(rng):
    return [{"bus128": rng.getrandbits(128)} for _ in range(2000)]
