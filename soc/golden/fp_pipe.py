"""Golden model of `fp_pipe`: three register stages for the FP side of the pipeline. Clocked. Written by hand. None before the first reset."""


def golden_fp_pipe(trace):
    st = None
    out = []
    for i in trace:
        if st is None:
            out.append({k: None for k in ("dwsel_ex", "dwsel_wb", "fres_wb", "flags_wb", "wrf_wb")})
        else:
            out.append({"dwsel_ex": st["ex"], "dwsel_wb": st["wb"][0], "fres_wb": st["wb"][1], "flags_wb": st["wb"][2], "wrf_wb": st["wb"][3]})
        zero = (0, 0, 0, 0)
        if i["rst"] & 1:
            st = {"ex": 0, "m": zero, "wb": zero}
        elif st is not None:
            ex = 0 if i["flush_ex"] else (st["ex"] if i["stall_ex"] else i["dwsel_id"])
            m = zero if i["flush_mem"] else (st["ex"], i["fres_ex"], i["flags_ex"], i["wrf_ex"])
            wb = zero if i["flush_wb"] else st["m"]
            st = {"ex": ex, "m": m, "wb": wb}
    return out


def traces(rng):
    out = []
    for _ in range(40):
        t = [{"rst": 1, "stall_ex": 0, "flush_ex": 0, "flush_mem": 0, "flush_wb": 0, "dwsel_id": 0, "fres_ex": 0, "flags_ex": 0, "wrf_ex": 0}]
        for _ in range(150):
            t.append({"rst": int(rng.random() < 0.01), "stall_ex": int(rng.random() < 0.3), "flush_ex": int(rng.random() < 0.1),
                      "flush_mem": int(rng.random() < 0.1), "flush_wb": int(rng.random() < 0.1), "dwsel_id": rng.getrandbits(2),
                      "fres_ex": rng.getrandbits(64), "flags_ex": rng.getrandbits(5), "wrf_ex": rng.getrandbits(1)})
        out.append(t)
    return out
