"""Golden model of `ps2_ctl`: Altera-UP-style PS/2 registers around an external receive queue. Clocked. Written by hand. None before the first reset."""


def golden_ps2_ctl(trace):
    st = None
    out = []
    for i in trace:
        reg1 = (i["addr"] >> 2) & 1
        if st is None:
            out.append({"rdata": None, "pop": None, "tx_start": None, "tx_data": None, "irq": None})
        else:
            re, ce = st
            cnt = i["count"] & 15
            if reg1 == 0:
                rd = (cnt << 16) | ((1 << 15) if cnt else 0) | (i["head"] & 0xFF)
            else:
                rd = re | ((1 << 8) if re and cnt else 0) | (ce << 10)
            out.append({"rdata": rd, "pop": int(bool(i["re_pulse"] & 1) and reg1 == 0),
                        "tx_start": int(bool(i["we"] & 1) and reg1 == 0 and not i["tx_busy"] & 1), "tx_data": i["wdata"] & 0xFF, "irq": int(bool(re and cnt))})
        if i["rst"] & 1:
            st = (0, 0)
        elif st is not None:
            re, ce = st
            if i["we"] & 1 and reg1 == 1:
                re, ce = i["wdata"] & 1, 0
            if (i["tx_done"] & 1) and (i["tx_err"] & 1):
                ce = 1
            st = (re, ce)
    return out


def traces(rng):
    out = []
    for _ in range(60):
        t = [{"rst": 1, "we": 0, "re_pulse": 0, "addr": 0, "wdata": 0, "head": 0, "count": 0, "tx_busy": 0, "tx_done": 0, "tx_err": 0}]
        for _ in range(250):
            t.append({"rst": int(rng.random() < 0.004), "we": int(rng.random() < 0.25), "re_pulse": int(rng.random() < 0.3), "addr": rng.getrandbits(32),
                      "wdata": rng.getrandbits(32), "head": rng.getrandbits(8), "count": rng.randrange(0, 9), "tx_busy": int(rng.random() < 0.3),
                      "tx_done": int(rng.random() < 0.1), "tx_err": int(rng.random() < 0.5)})
        out.append(t)
    return out
