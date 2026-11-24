"""Golden model of `ps2_fifo`: an 8-byte FIFO. Clocked. Written by hand. None before the first reset."""


def golden_ps2_fifo(trace):
    q = None
    out = []
    for i in trace:
        if q is None:
            out.append({"head": None, "count": None})
        else:
            out.append({"head": q[0] if q else 0, "count": len(q)})
        if i["rst"] & 1:
            q = []
        elif q is not None:
            q = list(q)
            if (i["pop"] & 1) and q:
                q.pop(0)
            if (i["push"] & 1) and len(q) < 8:
                q.append(i["din"] & 0xFF)
    return out


def traces(rng):
    out = []
    for _ in range(60):
        t = [{"rst": 1, "pop": 0, "push": 0, "din": 0}]
        pp, pq = rng.choice([(0.2, 0.5), (0.5, 0.3), (0.4, 0.4)])
        for _ in range(250):
            t.append({"rst": int(rng.random() < 0.004), "pop": int(rng.random() < pp), "push": int(rng.random() < pq), "din": rng.getrandbits(8)})
        out.append(t)
    return out
