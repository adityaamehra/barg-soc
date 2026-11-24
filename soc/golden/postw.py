"""Golden model of `postw`: marks a plain store handed to the memory engine as posted (the core goes on at the engine's start, not at its end). Clocked.
Written by hand. None before the first reset."""


def golden_postw(trace):
    pst = None
    out = []
    for i in trace:
        if pst is None:
            out.append({"wdone_o": None, "go0": None, "go1": None, "go2": None, "go3": None})
        else:
            posted = i["start"] & i["we"] & (1 - i["amo"]) & 1
            o = {"wdone_o": int((i["wdone"] and not pst) or posted)}
            for k in range(4):
                o[f"go{k}"] = int((i[f"g{k}"] and not pst) or (posted and i[f"b{k}"]))
            out.append(o)
        if i["rst"] & 1:
            pst = 0
        elif pst is not None:
            posted = i["start"] & i["we"] & (1 - i["amo"]) & 1
            if posted:
                pst = 1
            elif pst and i["wdone"]:
                pst = 0
    return out


def traces(rng):
    out = []
    for _ in range(40):
        t = [{"rst": 1, "start": 0, "we": 0, "amo": 0, "wdone": 0, "g0": 0, "g1": 0, "g2": 0, "g3": 0, "b0": 0, "b1": 0, "b2": 0, "b3": 0}]
        for _ in range(200):
            sel = rng.getrandbits(2)
            d = {"rst": int(rng.random() < 0.01), "start": int(rng.random() < 0.3), "we": rng.getrandbits(1), "amo": int(rng.random() < 0.3),
                 "wdone": int(rng.random() < 0.3)}
            for k in range(4):
                d[f"g{k}"] = int(rng.random() < 0.3)
                d[f"b{k}"] = int(k == sel and rng.random() < 0.8)
            t.append(d)
        out.append(t)
    return out
