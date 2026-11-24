"""Golden model of `ps2_rx`: PS/2 receiver (11-bit frames: start, 8 data LSB first, odd parity, stop). Clocked. Written by hand. None before the first reset."""


def golden_ps2_rx(trace):
    st = None
    out = []
    for i in trace:
        if st is None:
            out.append({"valid": None, "dout": None, "perr": None})
        else:
            out.append({"valid": st["valid"], "dout": st["byte"], "perr": st["perr"]})
        if i["rst"] & 1:
            st = {"c1": 1, "c2": 1, "c3": 1, "d1": 1, "d2": 1, "cnt": 0, "sh": 0, "idle": 0, "valid": 0, "byte": 0, "perr": 0}
        elif st is not None:
            n = dict(st)
            n["c1"], n["c2"], n["c3"], n["d1"], n["d2"] = i["clk_i"] & 1, st["c1"], st["c2"], i["dat_i"] & 1, st["d1"]
            n["valid"] = n["perr"] = 0
            fall = st["c3"] == 1 and st["c2"] == 0
            if fall:
                n["idle"] = 0
                sh = (st["sh"] & ~(1 << st["cnt"])) | (st["d2"] << st["cnt"])
                n["sh"] = sh & 0x7FF
                if st["cnt"] == 10:
                    n["cnt"] = 0
                    par = bin((sh >> 1) & 0x1FF).count("1") & 1
                    if (sh & 1) == 0 and st["d2"] == 1 and par == 1:
                        n["valid"], n["byte"] = 1, (sh >> 1) & 0xFF
                    else:
                        n["perr"] = 1
                else:
                    n["cnt"] = st["cnt"] + 1
            else:
                if st["idle"] != 65535:
                    n["idle"] = st["idle"] + 1
                if st["idle"] == 32767:
                    n["cnt"] = 0
            st = n
    return out


def _frame(byte, bad_parity=False, bad_stop=False):
    bits = [0] + [(byte >> k) & 1 for k in range(8)]
    par = 1 - (bin(byte).count("1") & 1)        # odd parity over the 8 data bits and the parity bit
    bits += [par ^ (1 if bad_parity else 0), 0 if bad_stop else 1]
    return bits


def traces(rng):
    out = []
    for _ in range(40):
        t = [{"rst": 1, "clk_i": 1, "dat_i": 1}]
        clk, dat = 1, 1
        for _ in range(rng.randrange(1, 5)):                      # a few frames, some damaged, with gaps; the clock edges are 6 cycles apart (a slow device clock)
            for _ in range(rng.randrange(3, 40)):
                t.append({"rst": 0, "clk_i": 1, "dat_i": 1})
            b = rng.getrandbits(8)
            bits = _frame(b, rng.random() < 0.15, rng.random() < 0.1)
            if rng.random() < 0.1:
                bits = bits[:rng.randrange(2, 10)]                # a frame cut short
            for v in bits:
                for k in range(6):
                    t.append({"rst": int(rng.random() < 0.002), "clk_i": 0 if k < 3 else 1, "dat_i": v})
        for _ in range(30):
            t.append({"rst": 0, "clk_i": rng.getrandbits(1), "dat_i": rng.getrandbits(1)})     # line noise
        out.append(t)
    t = [{"rst": 1, "clk_i": 1, "dat_i": 1}]                       # a frame cut short and then a stall of 40000 cycles: the partial frame must be dropped, the next one clean
    for v in _frame(0x5A)[:5]:
        for k in range(6):
            t.append({"rst": 0, "clk_i": 0 if k < 3 else 1, "dat_i": v})
    for _ in range(40000):
        t.append({"rst": 0, "clk_i": 1, "dat_i": 1})
    for v in _frame(0xA5):
        for k in range(6):
            t.append({"rst": 0, "clk_i": 0 if k < 3 else 1, "dat_i": v})
    for _ in range(20):
        t.append({"rst": 0, "clk_i": 1, "dat_i": 1})
    out.append(t)
    return out
