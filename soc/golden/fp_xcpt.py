"""Golden model of `fp_xcpt`: alignment trap of a double-word access. Combinational. Written by hand."""


def golden_fp_xcpt(xcpt_in, cause_in, tval_in, memwrite_in, is_store, dwsel, addr):
    bad = (not xcpt_in) and dwsel == 1 and (addr & 7) != 0
    return {"xcpt": int(bool(xcpt_in) or bad), "cause": (6 if is_store else 4) if bad else cause_in, "tval": addr if bad else tval_in,
            "memwrite_out": int(bool(memwrite_in) and not bad)}


def vectors(rng):
    return [{"xcpt_in": int(rng.random() < 0.3), "cause_in": rng.getrandbits(4), "tval_in": rng.getrandbits(32), "memwrite_in": rng.getrandbits(1),
             "is_store": rng.getrandbits(1), "dwsel": rng.choice((0, 1, 1, 2, 3)), "addr": rng.choice((0, 4, 8, rng.getrandbits(32), rng.getrandbits(32) & ~7))}
            for _ in range(3000)]
