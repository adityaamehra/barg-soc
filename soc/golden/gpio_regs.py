"""Golden model of `gpio_regs`: 16-pin GPIO registers with rising-edge interrupts. Clocked. Written by hand. None before the first reset."""


def golden_gpio_regs(trace):
    st = None
    out = []
    for i in trace:
        if st is None:
            out.append({"rdata": None, "gpio_out": None, "gpio_oe": None, "irq": None})
        else:
            r = (i["addr"] >> 2) & 3
            rd = st["s2"] if r == 0 else st["oe"] if r == 1 else st["ien"] if r == 2 else st["pend"]
            out.append({"rdata": rd, "gpio_out": st["out"], "gpio_oe": st["oe"], "irq": int((st["pend"] & st["ien"]) != 0)})
        if i["rst"] & 1:
            st = {"out": 0, "oe": 0, "ien": 0, "pend": 0, "s1": 0, "s2": 0, "prev": 0}
        elif st is not None:
            r = (i["addr"] >> 2) & 3
            we, wd = i["we"] & 1, i["wdata"] & 0xFFFF
            rise = st["s2"] & ~st["prev"] & 0xFFFF
            clr = wd if (we and r == 3) else 0
            n = dict(st)
            n["pend"] = (st["pend"] & ~clr & 0xFFFF) | rise
            if we and r == 0: n["out"] = wd
            if we and r == 1: n["oe"] = wd
            if we and r == 2: n["ien"] = wd
            n["prev"], n["s2"], n["s1"] = st["s2"], st["s1"], i["pins"] & 0xFFFF
            st = n
    return out


def traces(rng):
    out = []
    for _ in range(40):
        t = [{"rst": 1, "we": 0, "addr": 0, "wdata": 0, "pins": 0}]
        pins = 0
        for _ in range(200):
            if rng.random() < 0.4: pins ^= 1 << rng.randrange(16)
            if rng.random() < 0.05: pins = rng.getrandbits(16)
            t.append({"rst": int(rng.random() < 0.01), "we": int(rng.random() < 0.4), "addr": rng.choice([0, 4, 8, 12, rng.getrandbits(32)]),
                      "wdata": rng.choice([rng.getrandbits(32), 0xFFFF, 0, 1 << rng.randrange(16)]), "pins": pins})
        out.append(t)
    return out
