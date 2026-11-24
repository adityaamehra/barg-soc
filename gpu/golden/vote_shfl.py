"""Golden model of the vote and shuffle unit (block `vote_shfl`). Combinational.

simt_op 5 (vote): ballot = the active lanes (tmask) whose a_i is non-zero; every lane of y gets: mode 0 any (ballot != 0),
1 all (ballot == tmask), 2 ballot itself, 3 zero.
simt_op 6 (shfl): lane l of y = a of source lane s, whatever the mask: mode 0 idx s = b_l mod 4; 1 xor s = (l xor b_l) mod 4;
2 up s = l - b_l, or l when that is negative; 3 down s = l + b_l, or l when that is 4 or more (b_l unsigned).
Any other simt_op: y = 0.
"""

M = 0xFFFFFFFF


def golden_vote_shfl(simt_op, simt_mode, tmask, a, b):
    lane = lambda v, i: v >> 32 * i & M  # noqa: E731
    y = 0
    if simt_op == 5:
        ballot = sum(1 << i for i in range(4) if tmask >> i & 1 and lane(a, i))
        v = [int(ballot != 0), int(ballot == (tmask & 15)), ballot, 0][simt_mode & 3]
        for i in range(4):
            y |= v << 32 * i
    elif simt_op == 6:
        for l in range(4):
            k = lane(b, l)
            m = simt_mode & 3
            if m == 0:
                s = k % 4
            elif m == 1:
                s = (l ^ k) % 4
            elif m == 2:
                s = l - k if k <= l else l
            else:
                s = l + k if l + k < 4 else l
            y |= lane(a, s) << 32 * l
    return {"y": y}


def vectors(rng):
    """Directed vectors: vote and shuffle in every mode, every thread mask, small and large shuffle offsets, lanes of `a` that
    are zero and non-zero (a vote tests non-zero)."""
    out = []
    for _ in range(1500):
        lane = lambda: rng.choice((0, 1, 2, 3, 4, 5, 6, 0xFFFFFFFF, rng.getrandbits(32)))
        out.append({"simt_op": rng.choice((5, 6, 6, rng.randrange(8))), "simt_mode": rng.randrange(4), "tmask": rng.randrange(16),
                    "a": sum(lane() << 32 * i for i in range(4)), "b": sum(lane() << 32 * i for i in range(4))})
    return out
