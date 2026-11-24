"""Golden model of `spi_regs`: register file of an 8-bit SPI master. Clocked. Written by hand. None before the first reset."""


def golden_spi_regs(trace):
    st = None
    out = []
    for i in trace:
        r = (i["addr"] >> 2) & 7
        if st is None:
            out.append({"rdata": None, "tx_data": i["wdata"] & 0xFF, "tx_cs": None, "tx_valid": int(bool(i["we"] & 1 and r == 0 and i["tx_ready"] & 1)), "irq": None})
        else:
            rd = st["last"] if r == 0 else (st["busy"] | st["done"] << 1) if r == 1 else st["cs"] if r == 2 else st["ien"] if r == 3 else 0
            out.append({"rdata": rd, "tx_data": i["wdata"] & 0xFF, "tx_cs": st["cs"], "tx_valid": int(bool(i["we"] & 1 and r == 0 and i["tx_ready"] & 1)),
                        "irq": st["done"] & st["ien"]})
        if i["rst"] & 1:
            st = {"cs": 0, "last": 0, "done": 0, "busy": 0, "ien": 0}
        elif st is not None:
            we, tv = i["we"] & 1, bool(i["we"] & 1 and r == 0 and i["tx_ready"] & 1)
            n = dict(st)
            if tv: n["busy"] = 1
            if i["rx_valid"] & 1:
                n["busy"], n["done"], n["last"] = 0, 1, i["rx_data"] & 0xFF
            elif we and r == 1 and (i["wdata"] >> 1) & 1:
                n["done"] = 0
            if we and r == 2: n["cs"] = i["wdata"] & 3
            if we and r == 3: n["ien"] = i["wdata"] & 1
            st = n
    return out


def traces(rng):
    out = []
    for _ in range(40):
        t = [{"rst": 1, "we": 0, "addr": 0, "wdata": 0, "tx_ready": 1, "rx_data": 0, "rx_valid": 0}]
        for _ in range(200):
            t.append({"rst": int(rng.random() < 0.01), "we": int(rng.random() < 0.5), "addr": rng.choice([0, 4, 8, 12, 16, 20, rng.getrandbits(32)]),
                      "wdata": rng.getrandbits(32), "tx_ready": int(rng.random() < 0.7), "rx_data": rng.getrandbits(8), "rx_valid": int(rng.random() < 0.15)})
        out.append(t)
    return out
