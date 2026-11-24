"""Golden model of the SIMT control unit (block `simt_ctrl`). Combinational.

It decides the warp's next PC and thread mask at commit, and what the divergence stack, the spawner and the barriers do.
fa and fb are a and b of the lowest-numbered active lane (lane 0 when tmask is 0); p4 = pc + 4.

is_simt = valid & (unit == SIMT (4)). When is_simt is 0: c_pc = br_next_pc, c_tmask = tmask, and nothing else happens (every request below 0, err 0).
When is_simt is 1, by simt_op:
  0 tmc:    c_tmask = fa & 15, c_pc = p4, clear = 1 when that mask is 0 (the warp ends; its stack is emptied).
  1 wspawn: spawn_mask bit w (w = 1, 2, 3) is 1 when w < fa (unsigned); spawn_pc = fb; c_pc = p4.
  2 split:  pred = active lanes with a_i != 0; T = tmask & pred; F = tmask & ~pred. e0 = (tmask, pc 0, fall 1).
            Both T and F non-empty: push = 2, e1 = (F, p4, fall 0), c_tmask = T. Otherwise push = 1, c_tmask = tmask.
            c_pc = p4. err = 1 when depth + push > 8 (and then push = 0).
  3 join:   depth 0: err = 1, c_pc = p4, c_tmask = tmask. Otherwise pop = 1, c_tmask = top_mask,
            c_pc = p4 when top_fall is 1, else top_pc.
  4 bar:    bar_arrive = 1, bar_id = fa & 3, bar_count = min(fb, 7) (unsigned); err = 1 when fa > 3; c_pc = p4.
  5, 6 (vote, shfl): c_pc = p4 (the result comes from vote_shfl). 7: c_pc = p4.
Outputs not set are 0, except c_tmask (= tmask) and the entries' fields.
The requests push, pop, clear, spawn_mask and bar_arrive are 0 whenever advance is 0 (they act only at the edge where the
instruction completes); c_pc, c_tmask, the entries, spawn_pc, bar_id, bar_count and err do not depend on advance.
"""

M = 0xFFFFFFFF


def golden_simt_ctrl(valid, unit, advance, simt_op, tmask, pc, br_next_pc, a, b, top_mask, top_pc, top_fall, depth):
    out = _simt_ctrl(valid, unit, simt_op, tmask, pc, br_next_pc, a, b, top_mask, top_pc, top_fall, depth)
    if not advance & 1:
        out.update(push=0, pop=0, clear=0, spawn_mask=0, bar_arrive=0)
    return out


def _simt_ctrl(valid, unit, simt_op, tmask, pc, br_next_pc, a, b, top_mask, top_pc, top_fall, depth):
    tmask &= 15
    p4 = (pc + 4) & M
    out = {"c_pc": br_next_pc & M, "c_tmask": tmask, "push": 0, "e0_mask": 0, "e0_pc": 0, "e0_fall": 0,
           "e1_mask": 0, "e1_pc": 0, "e1_fall": 0, "pop": 0, "clear": 0, "spawn_mask": 0, "spawn_pc": 0,
           "bar_arrive": 0, "bar_id": 0, "bar_count": 0, "err": 0}
    if not (valid & 1 and unit == 4):
        return out
    lanes = [i for i in range(4) if tmask >> i & 1] or [0]
    fa, fb = a >> 32 * lanes[0] & M, b >> 32 * lanes[0] & M
    out["c_pc"] = p4
    if simt_op == 0:
        out["c_tmask"] = fa & 15
        out["clear"] = int(fa & 15 == 0)
    elif simt_op == 1:
        out["spawn_mask"] = sum(1 << w for w in (1, 2, 3) if w < fa)
        out["spawn_pc"] = fb
    elif simt_op == 2:
        pred = sum(1 << i for i in range(4) if tmask >> i & 1 and a >> 32 * i & M)
        t, f = tmask & pred, tmask & ~pred & 15
        push = 2 if t and f else 1
        if depth + push > 8:
            out["err"] = 1
        else:
            out.update(push=push, e0_mask=tmask, e0_pc=0, e0_fall=1)
            if push == 2:
                out.update(e1_mask=f, e1_pc=p4, e1_fall=0, c_tmask=t)
    elif simt_op == 3:
        if depth == 0:
            out["err"] = 1
        else:
            out.update(pop=1, c_tmask=top_mask & 15, c_pc=p4 if top_fall & 1 else top_pc & M)
    elif simt_op == 4:
        out.update(bar_arrive=1, bar_id=fa & 3, bar_count=min(fb, 7), err=int(fa > 3))
    return out


def vectors(rng):
    """Directed vectors: every SIMT instruction, with legal stack depths (0 to 8), small operands where an instruction uses
    them as a count or an id, every thread mask, advance high and low."""
    out = []
    for _ in range(1500):
        op = rng.randrange(8)
        small = lambda: sum(rng.choice((0, 1, 2, 3, 4, 5, 7, 8, 100, rng.getrandbits(32))) << 32 * i for i in range(4))
        out.append({"valid": 1 if rng.random() < 0.97 else 0, "unit": 4 if rng.random() < 0.97 else rng.randrange(8),
                    "advance": rng.randrange(2), "simt_op": op, "tmask": rng.randrange(16), "pc": rng.getrandbits(32) & ~3,
                    "br_next_pc": rng.getrandbits(32) & ~3, "a": small() if rng.random() < 0.6 else rng.getrandbits(128),
                    "b": small() if rng.random() < 0.6 else rng.getrandbits(128), "top_mask": rng.randrange(16),
                    "top_pc": rng.getrandbits(32) & ~3, "top_fall": rng.randrange(2), "depth": rng.randrange(9)})
    return out
