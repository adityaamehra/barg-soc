"""Golden model of `rsp_hold`: the last memory response, held. Clocked. Written by hand. None before the first reset."""


def golden_rsp_hold(trace):
    held = None
    out = []
    for i in trace:
        if held is None:
            out.append({"data": None, "word": None})
        else:
            d = i["line"] if i["done"] & 1 else held
            out.append({"data": d, "word": d & 0xFFFFFFFF})
        if i["rst"] & 1:
            held = 0
        elif held is not None and i["done"] & 1:
            held = i["line"]
    return out


def traces(rng):
    out = []
    for _ in range(40):
        t = [{"rst": 1, "done": 0, "line": 0}]
        for _ in range(120):
            t.append({"rst": int(rng.random() < 0.01), "done": int(rng.random() < 0.3), "line": rng.getrandbits(256)})
        out.append(t)
    return out
