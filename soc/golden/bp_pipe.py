"""Golden model of `bp_pipe`: the prediction carried from fetch through decode to execute. Clocked. Written by hand. None before the first reset."""


def golden_bp_pipe(trace):
    st = None
    out = []
    for i in trace:
        out.append({"pt_ex": None, "ptarget_ex": None, "pidx_ex": None} if st is None else {"pt_ex": st[1][0], "ptarget_ex": st[1][1], "pidx_ex": st[1][2]})
        zero = (0, 0, 0)
        if i["rst"] & 1:
            st = (zero, zero)
        elif st is not None:
            idv, exv = st
            new_ex = zero if i["flush_id"] else (exv if i["stall_id"] else idv)
            new_id = zero if i["flush_if"] else (idv if i["stall_if"] else (i["pt_if"], i["ptarget_if"], i["pidx_if"]))
            st = (new_id, new_ex)
    return out


def traces(rng):
    out = []
    for _ in range(40):
        t = [{"rst": 1, "stall_if": 0, "flush_if": 0, "stall_id": 0, "flush_id": 0, "pt_if": 0, "ptarget_if": 0, "pidx_if": 0}]
        for _ in range(150):
            t.append({"rst": int(rng.random() < 0.01), "stall_if": int(rng.random() < 0.3), "flush_if": int(rng.random() < 0.1), "stall_id": int(rng.random() < 0.3),
                      "flush_id": int(rng.random() < 0.1), "pt_if": rng.getrandbits(1), "ptarget_if": rng.getrandbits(32), "pidx_if": rng.getrandbits(8)})
        out.append(t)
    return out
