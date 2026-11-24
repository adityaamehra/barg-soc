"""Golden model of `dcache_ctl`: the data cache's controller. Clocked. Written by hand. None before the first reset."""
M32 = 0xFFFFFFFF


def golden_dcache_ctl(trace):
    st = None
    out = []
    for i in trace:
        is_load = (i["req"] & 1) & (i["is_ram"] & 1) & (1 - (i["is_store"] & 1)) & (1 - (i["is_amo"] & 1)) & (1 - (i["hold"] & 1))
        serve = is_load & (i["hit"] & 1)
        dmiss = is_load & (1 - (i["hit"] & 1))
        plain_self = (i["self"] & 1) & (i["w_plain"] & 1)
        if st is None:
            out.append({k: None for k in ("serve", "dmiss", "rq", "rq_addr", "fill_en", "fill_addr", "fill_data", "wr_en", "wr_addr", "inv_en", "inv_addr")})
        else:
            ra, busy = st
            out.append({"serve": serve, "dmiss": dmiss, "rq": busy, "rq_addr": ra, "fill_en": busy & (i["done"] & 1), "fill_addr": ra,
                        "fill_data": i["line"], "wr_en": (i["wdone"] & 1) & plain_self, "wr_addr": i["waddr"],
                        "inv_en": (i["wdone"] & 1) & (1 - plain_self), "inv_addr": i["waddr"]})
        if i["rst"] & 1:
            st = (0, 0)
        elif st is not None:
            ra, busy = st
            if busy == 0 and dmiss:
                ra = (i["addr"] & M32) & ~31
                busy = 1
            elif busy == 1 and i["done"] & 1:
                busy = 0
            st = (ra, busy)
    return out


def traces(rng):
    out = []
    for _ in range(60):
        t = [{"rst": 1, "req": 0, "is_ram": 0, "is_store": 0, "is_amo": 0, "hit": 0, "hold": 0, "addr": 0, "done": 0, "line": 0, "wdone": 0, "waddr": 0,
              "self": 0, "w_plain": 0}]
        for _ in range(160):
            t.append({"rst": int(rng.random() < 0.01), "req": int(rng.random() < 0.7), "is_ram": int(rng.random() < 0.8), "is_store": int(rng.random() < 0.3),
                      "is_amo": int(rng.random() < 0.15), "hit": int(rng.random() < 0.5), "hold": int(rng.random() < 0.15), "addr": rng.getrandbits(32),
                      "done": int(rng.random() < 0.3), "line": rng.getrandbits(256), "wdone": int(rng.random() < 0.3), "waddr": rng.getrandbits(32),
                      "self": int(rng.random() < 0.5), "w_plain": int(rng.random() < 0.6)})
        out.append(t)
    return out
