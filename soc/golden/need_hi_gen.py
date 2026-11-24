"""Golden model of `need_hi_gen`: the fetched instruction straddles into the next word. Combinational. Written by hand."""


def golden_need_hi_gen(pc, word_lo):
    return {"need_hi": int(((pc >> 1) & 1) == 1 and ((word_lo >> 16) & 3) == 3)}


def vectors(rng):
    return [{"pc": rng.getrandbits(32), "word_lo": rng.getrandbits(32)} for _ in range(500)]
