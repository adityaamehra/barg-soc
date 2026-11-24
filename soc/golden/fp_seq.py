"""Golden model of `fp_seq`: start-once sequencer with a latched result. Clocked. Written by hand. None before the first reset."""


def golden_fp_seq(trace):
    s = None
    out = []
    for i in trace:
        if s is None:
            out.append({k: None for k in ("start", "busy", "fres", "ires", "flags", "wrf")})
        else:
            out.append({"start": int(bool(i["is_fpu"]) and s["st"] == 0), "busy": int(bool(i["is_fpu"]) and s["st"] != 2),
                        "fres": s["fres"], "ires": s["ires"], "flags": s["flags"], "wrf": s["wrf"]})
        if i["rst"] & 1:
            s = {"st": 0, "fres": 0, "ires": 0, "flags": 0, "wrf": 0}
        elif s is not None:
            if s["st"] == 0 and i["is_fpu"]:
                s["st"] = 1
            elif s["st"] == 1 and i["done"]:
                s.update(fres=i["fres_in"], ires=i["ires_in"], flags=i["flags_in"], wrf=i["wrf_in"], st=2)
            elif s["st"] == 2:
                s["st"] = 0
    return out


def traces(rng):
    out = []
    for _ in range(40):
        t = [{"rst": 1, "is_fpu": 0, "done": 0, "fres_in": 0, "ires_in": 0, "flags_in": 0, "wrf_in": 0}]
        for _ in range(150):
            t.append({"rst": int(rng.random() < 0.01), "is_fpu": int(rng.random() < 0.6), "done": int(rng.random() < 0.3),
                      "fres_in": rng.getrandbits(64), "ires_in": rng.getrandbits(32), "flags_in": rng.getrandbits(5), "wrf_in": rng.getrandbits(1)})
        out.append(t)
    return out
