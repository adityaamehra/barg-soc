"""Golden model of `fp_dwseq`: the double-word split sequencer. Clocked. Written by hand. None before the first reset."""
M32 = 0xFFFFFFFF


def golden_fp_dwseq(trace):
    half2 = None
    out = []
    for i in trace:
        dw = None
        if half2 is not None:
            dw = int(bool(i["is_dw"]) and bool(i["valid"]) and not i["xcpt"])
            out.append({"half2": half2, "hold": int(bool(dw) and not half2),
                        "dwsel": 0 if not dw else (2 if half2 else 1), "imm_out": (i["imm_in"] + (4 if dw and half2 else 0)) & M32})
        else:
            out.append({"half2": None, "hold": None, "dwsel": None, "imm_out": None})
        if i["rst"] & 1:
            half2 = 0
        elif half2 is not None:
            accept = not i["stall"] and not i["flush"]
            if i["flush"]:
                half2 = 0
            elif dw and accept:
                half2 = 1 - half2
            elif not dw:
                half2 = 0
    return out


def traces(rng):
    out = []
    for _ in range(40):
        t = [{"rst": 1, "is_dw": 0, "valid": 0, "xcpt": 0, "stall": 0, "flush": 0, "imm_in": 0}]
        for _ in range(150):
            t.append({"rst": int(rng.random() < 0.01), "is_dw": int(rng.random() < 0.6), "valid": int(rng.random() < 0.85),
                      "xcpt": int(rng.random() < 0.1), "stall": int(rng.random() < 0.25), "flush": int(rng.random() < 0.1),
                      "imm_in": rng.choice((0, 4, 0xFFFFFFFC, 0x7FC, rng.getrandbits(32)))})
        out.append(t)
    return out
