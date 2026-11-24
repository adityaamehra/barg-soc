"""Golden model of `src_mux3`: a, b or c by a 2-bit source, 0 for source 3. Combinational. Written by hand."""


def golden_src_mux3(src, a, b, c):
    return {"y": (a, b, c, 0)[src & 3] & 0xFFFFFFFF}


def vectors(rng):
    return [{"src": rng.getrandbits(2), "a": rng.getrandbits(32), "b": rng.getrandbits(32), "c": rng.getrandbits(32)} for _ in range(400)]
