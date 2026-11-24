"""Golden model of `i2c_regs`: register file of a byte-wise I2C master. Clocked. Written by hand. None before the first reset."""


def golden_i2c_regs(trace):
    st = None
    out = []
    for i in trace:
        r = (i["addr"] >> 2) & 7
        cv = int(bool(i["we"] & 1 and r == 0 and i["cmd_ready"] & 1))
        w = i["wdata"]
        o = {"cmd_valid": cv, "cmd_op": (w >> 11) & 3, "cmd_start": (w >> 8) & 1, "cmd_stop": (w >> 9) & 1, "cmd_nack": (w >> 10) & 1, "cmd_data": w & 0xFF}
        if st is None:
            o.update({"rdata": None, "irq": None})
        else:
            rd = st["last"] if r == 0 else (st["busy"] | st["done"] << 1 | st["nack"] << 2 | st["arb"] << 3) if r == 1 else st["ien"] if r == 3 else 0
            o.update({"rdata": rd, "irq": st["done"] & st["ien"]})
        out.append(o)
        if i["rst"] & 1:
            st = {"last": 0, "done": 0, "busy": 0, "nack": 0, "arb": 0, "ien": 0}
        elif st is not None:
            we = i["we"] & 1
            n = dict(st)
            if cv: n["busy"] = 1
            if i["rsp_valid"] & 1:
                n.update({"busy": 0, "done": 1, "last": i["rsp_data"] & 0xFF, "nack": i["rsp_nack"] & 1, "arb": i["rsp_arb_lost"] & 1})
            elif we and r == 1 and (w >> 1) & 1:
                n.update({"done": 0, "nack": 0, "arb": 0})
            if we and r == 3: n["ien"] = w & 1
            st = n
    return out


def traces(rng):
    out = []
    for _ in range(40):
        t = [{"rst": 1, "we": 0, "addr": 0, "wdata": 0, "cmd_ready": 1, "rsp_valid": 0, "rsp_data": 0, "rsp_nack": 0, "rsp_arb_lost": 0}]
        for _ in range(200):
            t.append({"rst": int(rng.random() < 0.01), "we": int(rng.random() < 0.5), "addr": rng.choice([0, 4, 8, 12, 16, rng.getrandbits(32)]),
                      "wdata": rng.getrandbits(32), "cmd_ready": int(rng.random() < 0.7), "rsp_valid": int(rng.random() < 0.15), "rsp_data": rng.getrandbits(8),
                      "rsp_nack": rng.getrandbits(1), "rsp_arb_lost": int(rng.random() < 0.2)})
        out.append(t)
    return out
