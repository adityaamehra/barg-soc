"""Golden model of `unpack16`: a 512-bit bus of sixteen 32-bit words (w0 in bits 31:0). Written by hand."""


def golden_unpack16(bus512):
    return {f"w{k}": (bus512 >> 32 * k) & 0xFFFFFFFF for k in range(16)}


def vectors(rng):
    return [{"bus512": rng.getrandbits(512)} for _ in range(1500)]
