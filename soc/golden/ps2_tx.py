"""Golden model of `ps2_tx`: PS/2 host-to-device transmitter. Clocked. Written by hand. None before the first reset."""


def golden_ps2_tx(trace):
    st = None
    out = []
    for i in trace:
        if st is None:
            out.append({k: None for k in ("clk_low", "dat_low", "busy", "done", "err")})
        else:
            s, n = st["st"], st["n"]
            dat_low = int(s == 2 and (n <= 1 or (2 <= n <= 10 and ((st["sh"] >> (n - 2)) & 1) == 0)))
            out.append({"clk_low": int(s == 1), "dat_low": dat_low, "busy": int(s != 0), "done": st["done"], "err": st["err"]})
        if i["rst"] & 1:
            st = {"c1": 1, "c2": 1, "c3": 1, "d1": 1, "d2": 1, "st": 0, "hold": 0, "n": 0, "sh": 0, "done": 0, "err": 0}
        elif st is not None:
            m = dict(st)
            m["c1"], m["c2"], m["c3"], m["d1"], m["d2"] = i["clk_i"] & 1, st["c1"], st["c2"], i["dat_i"] & 1, st["d1"]
            m["done"] = 0
            fall = st["c3"] == 1 and st["c2"] == 0
            rise = st["c3"] == 0 and st["c2"] == 1
            if st["st"] == 0:
                if i["start"] & 1:
                    d = i["data"] & 0xFF
                    par = 1 if bin(d).count("1") % 2 == 0 else 0
                    m["sh"], m["hold"], m["err"], m["st"] = d | (par << 8), 0, 0, 1
            elif st["st"] == 1:
                m["hold"] = (st["hold"] + 1) & 0x3FFF
                if st["hold"] == 16383:
                    m["st"], m["n"] = 2, 0
            else:
                if fall:
                    m["n"] = (st["n"] + 1) & 15
                if st["n"] == 12 and rise:
                    m["done"], m["err"], m["st"] = 1, st["d2"], 0
            st = m
    return out


def traces(rng):
    out = []
    def clocks(t, n_pulses, dev_ack, data_pat):
        """A device that, once the request is seen, makes n_pulses clock pulses (6 cycles low, 6 cycles high)."""
        for p in range(n_pulses):
            for k in range(12):
                t.append({"rst": 0, "clk_i": 0 if k < 6 else 1, "dat_i": 0 if (p == 11 and dev_ack) else 1, "start": 0, "data": 0})
    for _ in range(6):
        t = [{"rst": 1, "clk_i": 1, "dat_i": 1, "start": 0, "data": 0}]
        for _ in range(10):
            t.append({"rst": 0, "clk_i": 1, "dat_i": 1, "start": 0, "data": 0})
        t.append({"rst": 0, "clk_i": 1, "dat_i": 1, "start": 1, "data": rng.getrandbits(8)})
        for _ in range(16450):                                    # inhibit, then the request
            t.append({"rst": 0, "clk_i": 1, "dat_i": 1, "start": int(rng.random() < 0.01), "data": rng.getrandbits(8)})
        clocks(t, 12, rng.random() < 0.7, None)
        for _ in range(30):
            t.append({"rst": 0, "clk_i": 1, "dat_i": 1, "start": 0, "data": 0})
        out.append(t)
    t = [{"rst": 1, "clk_i": 1, "dat_i": 1, "start": 0, "data": 0}]      # random lines while idle: nothing may happen without start
    for _ in range(400):
        t.append({"rst": int(rng.random() < 0.01), "clk_i": rng.getrandbits(1), "dat_i": rng.getrandbits(1), "start": 0, "data": rng.getrandbits(8)})
    out.append(t)
    return out
