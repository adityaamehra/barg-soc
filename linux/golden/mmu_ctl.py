"""Golden model of `mmu_ctl`: when the core must wait for a page-table walk, and what to walk. Combinational. Written by hand."""


def golden_mmu_ctl(xlate_i, xlate_d, d_access, word_lo, lo_miss, hi_miss, d_miss, ptw_busy, pc, hi_addr, d_va):
    need_hi = (pc >> 1 & 1) and (word_lo >> 16 & 3) == 3
    lm = bool(xlate_i & 1) and bool(lo_miss & 1)
    hm = bool(xlate_i & 1) and not lo_miss & 1 and bool(need_hi) and bool(hi_miss & 1)
    dm = bool(xlate_d & 1) and bool(d_access & 1) and bool(d_miss & 1)
    busy = bool(ptw_busy & 1)
    return {"stall": int(busy or lm or hm or dm), "walk_start": int(not busy and (lm or hm or dm)),
            "walk_va": (d_va if dm else pc if lm else hi_addr if hm else 0) & 0xFFFFFFFF}


def vectors(rng):
    return [{"xlate_i": rng.getrandbits(1), "xlate_d": rng.getrandbits(1), "d_access": rng.getrandbits(1), "word_lo": rng.getrandbits(32),
             "lo_miss": rng.getrandbits(1), "hi_miss": rng.getrandbits(1), "d_miss": rng.getrandbits(1), "ptw_busy": int(rng.random() < 0.3),
             "pc": rng.getrandbits(32), "hi_addr": rng.getrandbits(32), "d_va": rng.getrandbits(32)} for _ in range(4000)]
