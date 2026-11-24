"""Golden model of `l2_ctl_fw`: the mid-level cache controller (two arrays, write-through). Clocked. Written by hand. None before the first reset."""
M32 = 0xFFFFFFFF
IDLE, LOOK, DREQ, DWAIT, FILL, RESP = range(6)


def golden_l2_ctl_fw(trace):
    st = None
    out = []
    for i in trace:
        if st is None:
            out.append({k: None for k in ("ready", "resp_valid", "resp_data", "lk_addr", "dv", "dwe", "dline", "daddr", "dwdata", "dwstrb", "fill_a_en",
                                          "fill_b_en", "fill_addr", "fill_data", "inv_en", "inv_addr")})
        else:
            s, we, ln, pr, f, ad, wd, ws, dq = st
            if s > RESP:
                s = IDLE
            rd = 0
            if s == RESP and not we:
                rd = (i["line_b"] if pr else i["line_a"]) if f else dq
            out.append({"ready": int(s == IDLE), "resp_valid": int(s == RESP or (s == DWAIT and bool(i["d_valid"] & 1) and bool(we))), "resp_data": rd, "lk_addr": ad, "dv": int(s == DREQ), "dwe": we, "dline": ln,
                        "daddr": ad, "dwdata": wd, "dwstrb": ws, "fill_a_en": int(s == FILL and not pr), "fill_b_en": int(s == FILL and bool(pr)),
                        "fill_addr": ad, "fill_data": dq, "inv_en": int(s == IDLE and bool(i["rv"] & 1) and bool(i["rwe"] & 1)), "inv_addr": (i["raddr"] & M32) if s == IDLE else ad})
        if i["rst"] & 1:
            st = (IDLE, 0, 0, 0, 0, 0, 0, 0, 0)
        elif st is not None:
            s, we, ln, pr, f, ad, wd, ws, dq = st
            if s > RESP:
                s = IDLE
            if s == IDLE:
                if i["rv"] & 1:
                    we, ln, ad, wd, ws, pr = i["rwe"] & 1, i["rline"] & 1, i["raddr"] & M32, i["rwdata"] & M32, i["rwstrb"] & 15, i["pair"] & 1
                    s = DREQ if i["rwe"] & 1 else LOOK
            elif s == LOOK:
                hit = (i["hit_b"] if pr else i["hit_a"]) & 1
                if not we and ln and hit:
                    f, s = 1, RESP
                else:
                    f, s = 0, DREQ
            elif s == DREQ:
                s = DWAIT if i["d_ready"] & 1 else s
            elif s == DWAIT:
                if i["d_valid"] & 1:
                    dq = i["d_data"]
                    s = FILL if (not we and ln) else (IDLE if we else RESP)
            elif s == FILL:
                s = RESP
            elif s == RESP:
                s = IDLE
            st = (s, we, ln, pr, f, ad, wd, ws, dq)
    return out


def traces(rng):
    out = []
    for _ in range(60):
        t = [{"rst": 1, "rv": 0, "rwe": 0, "rline": 0, "raddr": 0, "rwdata": 0, "rwstrb": 0, "pair": 0, "hit_a": 0, "hit_b": 0, "line_a": 0, "line_b": 0,
              "d_ready": 0, "d_valid": 0, "d_data": 0}]
        for _ in range(200):
            t.append({"rst": int(rng.random() < 0.005), "rv": int(rng.random() < 0.4), "rwe": int(rng.random() < 0.4), "rline": int(rng.random() < 0.6),
                      "raddr": rng.getrandbits(32), "rwdata": rng.getrandbits(32), "rwstrb": rng.getrandbits(4), "pair": rng.getrandbits(1),
                      "hit_a": int(rng.random() < 0.5), "hit_b": int(rng.random() < 0.5), "line_a": rng.getrandbits(256), "line_b": rng.getrandbits(256),
                      "d_ready": int(rng.random() < 0.5), "d_valid": int(rng.random() < 0.3), "d_data": rng.getrandbits(256)})
        out.append(t)
    return out
