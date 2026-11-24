"""Golden model of `ifetch_ctl`: the instruction-fetch refill controller. Clocked. Written by hand. Outputs before the edge; None before the first reset."""
M32 = 0xFFFFFFFF


def golden_ifetch_ctl(trace):
    st = None
    out = []
    for i in trace:
        miss_lo = 1 - (i["hit_lo"] & 1)
        miss_hi = (i["need_hi"] & 1) & (1 - (i["hit_hi"] & 1))
        imiss = (miss_lo | miss_hi) & (1 - (i["hold"] & 1))
        if st is None:
            out.append({k: None for k in ("imiss", "rq", "rq_addr", "fill_en", "fill_addr", "fill_data", "inv_all")})
        else:
            ra, busy = st
            out.append({"imiss": imiss, "rq": busy, "rq_addr": ra, "fill_en": busy & (i["done"] & 1), "fill_addr": ra,
                        "fill_data": i["line"], "inv_all": (i["fence"] & 1) & (i["adv"] & 1)})
        if i["rst"] & 1:
            st = (0, 0)
        elif st is not None:
            ra, busy = st
            if busy == 0 and imiss:
                ra = ((i["lo_addr"] if miss_lo else i["hi_addr"]) & M32) & ~31
                busy = 1
            elif busy == 1 and i["done"] & 1:
                busy = 0
            st = (ra, busy)
    return out


def traces(rng):
    out = []
    for _ in range(60):
        t = [{"rst": 1, "hit_lo": 0, "hit_hi": 0, "need_hi": 0, "hold": 0, "lo_addr": 0, "hi_addr": 0, "done": 0, "line": 0, "fence": 0, "adv": 0}]
        for _ in range(160):
            t.append({"rst": int(rng.random() < 0.01), "hit_lo": int(rng.random() < 0.5), "hit_hi": int(rng.random() < 0.5),
                      "need_hi": int(rng.random() < 0.4), "hold": int(rng.random() < 0.15), "lo_addr": rng.getrandbits(32),
                      "hi_addr": rng.getrandbits(32), "done": int(rng.random() < 0.3), "line": rng.getrandbits(256),
                      "fence": int(rng.random() < 0.2), "adv": int(rng.random() < 0.5)})
        out.append(t)
    return out
