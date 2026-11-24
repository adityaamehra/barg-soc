"""Golden model of the four-core bus arbiter (block `bus_arb`). Clocked. Written by hand.

Register last (2 bits, 3 at reset). grant<k> (combinational, from last and req0..req3): the first core that requests in the order
last+1, last+2, last+3, last (mod 4) gets the grant; at most one grant, none when nobody requests. run<k> = !req<k> | grant<k>.
At each rising edge: reset sets last to 3; else when a grant is given, last is the core that got it."""


def _grant(last, req):
    for d in (1, 2, 3, 4):
        k = (last + d) % 4
        if req[k]:
            return k
    return None


def golden_bus_arb(trace):
    last, out = None, []
    for s in trace:
        req = [s[f"req{k}"] & 1 for k in range(4)]
        g = None if last is None else _grant(last, req)
        out.append({**{f"grant{k}": None if last is None else int(g == k) for k in range(4)},
                    **{f"run{k}": None if last is None else int(not req[k] or g == k) for k in range(4)}})
        if s["rst"] & 1:
            last = 3
        elif g is not None:
            last = g
    return out


def traces(rng):
    out = []
    for _ in range(40):
        t = [{"rst": 1, **{f"req{k}": 0 for k in range(4)}}]
        p = rng.choice([0.2, 0.5, 0.9])
        for _ in range(150):
            t.append({"rst": int(rng.random() < 0.01), **{f"req{k}": int(rng.random() < p) for k in range(4)}})
        out.append(t)
    return out
