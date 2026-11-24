"""Golden model of `l3_ctl_wa`: the last-level cache controller, write-allocate (a write miss fills the line first, then writes the word). Clocked. Written by hand. None before the first reset."""
M32 = 0xFFFFFFFF
IDLE, LOOK, WBREQ, WBWAIT, FREQ, FWAIT, FILL, WR, AREQ, AWAIT, RESP = range(11)


def golden_l3_ctl_wa(trace):
    st = None
    out = []
    for i in trace:
        if st is None:
            out.append({k: None for k in ("ready", "resp_valid", "resp_data", "lk_addr", "fill_en", "fill_addr", "fill_data", "wr_en", "wr_addr", "wr_data",
                                          "wr_be", "ax_valid", "ax_we", "ax_line", "ax_addr", "ax_wdata", "ax_wstrb", "ax_wline")})
        else:
            s, we, ln, ad, wd, ws = st
            if s > RESP:
                s = IDLE
            rd = 0
            if s == RESP and not we:
                rd = i["lk_line"] if ln else (i["lk_line"] >> (32 * ((ad >> 2) & 7))) & M32
            axa = {WBREQ: i["vic_addr"], FREQ: ad & ~31, AREQ: ad & ~3}.get(s, 0)
            out.append({"ready": int(s == IDLE), "resp_valid": int(s == RESP), "resp_data": rd, "lk_addr": ad, "fill_en": int(s == FILL), "fill_addr": ad,
                        "fill_data": i["ax_data"], "wr_en": int(s == WR), "wr_addr": ad, "wr_data": wd, "wr_be": ws, "ax_valid": int(s in (WBREQ, FREQ, AREQ)),
                        "ax_we": int(s in (WBREQ, AREQ)), "ax_line": int(s in (WBREQ, FREQ)), "ax_addr": axa & M32, "ax_wdata": wd, "ax_wstrb": ws,
                        "ax_wline": i["vic_data"]})
        if i["rst"] & 1:
            st = (IDLE, 0, 0, 0, 0, 0)
        elif st is not None:
            s, we, ln, ad, wd, ws = st
            if s > RESP:
                s = IDLE
            if s == IDLE:
                if i["rv"] & 1:
                    we, ln, ad, wd, ws = i["rwe"] & 1, i["rline"] & 1, i["raddr"] & M32, i["rwdata"] & M32, i["rwstrb"] & 15
                    s = LOOK
            elif s == LOOK:
                if not we:
                    s = RESP if i["hit"] & 1 else (WBREQ if (i["vic_valid"] & 1) and (i["vic_dirty"] & 1) else FREQ)
                else:
                    s = WR if i["hit"] & 1 else (WBREQ if (i["vic_valid"] & 1) and (i["vic_dirty"] & 1) else FREQ)
            elif s == WBREQ:
                s = WBWAIT if i["ax_ready"] & 1 else s
            elif s == WBWAIT:
                s = FREQ if i["ax_done"] & 1 else s
            elif s == FREQ:
                s = FWAIT if i["ax_ready"] & 1 else s
            elif s == FWAIT:
                s = FILL if i["ax_done"] & 1 else s
            elif s == FILL:
                s = WR if we else RESP
            elif s == WR:
                s = RESP
            elif s == AREQ:
                s = AWAIT if i["ax_ready"] & 1 else s
            elif s == AWAIT:
                s = RESP if i["ax_done"] & 1 else s
            elif s == RESP:
                s = IDLE
            st = (s, we, ln, ad, wd, ws)
    return out


def traces(rng):
    out = []
    for _ in range(60):
        t = [{"rst": 1, "rv": 0, "rwe": 0, "rline": 0, "raddr": 0, "rwdata": 0, "rwstrb": 0, "hit": 0, "lk_line": 0, "vic_valid": 0, "vic_dirty": 0,
              "vic_addr": 0, "vic_data": 0, "ax_ready": 0, "ax_done": 0, "ax_data": 0}]
        for _ in range(200):
            t.append({"rst": int(rng.random() < 0.005), "rv": int(rng.random() < 0.4), "rwe": int(rng.random() < 0.5), "rline": int(rng.random() < 0.5),
                      "raddr": rng.getrandbits(32), "rwdata": rng.getrandbits(32), "rwstrb": rng.getrandbits(4), "hit": int(rng.random() < 0.5),
                      "lk_line": rng.getrandbits(256), "vic_valid": int(rng.random() < 0.6), "vic_dirty": int(rng.random() < 0.5),
                      "vic_addr": rng.getrandbits(32), "vic_data": rng.getrandbits(256), "ax_ready": int(rng.random() < 0.5),
                      "ax_done": int(rng.random() < 0.3), "ax_data": rng.getrandbits(256)})
        out.append(t)
    return out
