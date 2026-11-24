"""Golden model of `ps2_regs`: Altera-UP-style PS/2 registers with an 8-byte receive FIFO. Clocked. Written by hand. None before the first reset."""


def golden_ps2_regs(trace):
    st = None
    out = []
    for i in trace:
        if st is None:
            out.append({"rdata": None, "tx_start": None, "tx_data": None, "irq": None})
        else:
            fifo, re, ce = st
            cnt = len(fifo)
            reg1 = (i["addr"] >> 2) & 1
            if reg1 == 0:
                rd = (cnt << 16) | ((1 << 15) if cnt else 0) | (fifo[0] if cnt else 0)
            else:
                rd = re | ((1 << 8) if re and cnt else 0) | (ce << 10)
            out.append({"rdata": rd, "tx_start": int(bool(i["we"] & 1) and reg1 == 0 and not i["tx_busy"] & 1), "tx_data": i["wdata"] & 0xFF, "irq": int(bool(re and cnt))})
        if i["rst"] & 1:
            st = ([], 0, 0)
        elif st is not None:
            fifo, re, ce = list(st[0]), st[1], st[2]
            reg1 = (i["addr"] >> 2) & 1
            if (i["re_pulse"] & 1) and reg1 == 0 and fifo:
                fifo.pop(0)
            if i["rx_valid"] & 1 and len(fifo) < 8:
                fifo.append(i["rx_byte"] & 0xFF)
            if i["we"] & 1 and reg1 == 1:
                re, ce = i["wdata"] & 1, 0
            if (i["tx_done"] & 1) and (i["tx_err"] & 1):
                ce = 1
            st = (fifo, re, ce)
    return out


def traces(rng):
    out = []
    for _ in range(60):
        t = [{"rst": 1, "we": 0, "re_pulse": 0, "addr": 0, "wdata": 0, "rx_valid": 0, "rx_byte": 0, "tx_busy": 0, "tx_done": 0, "tx_err": 0}]
        for _ in range(250):
            t.append({"rst": int(rng.random() < 0.004), "we": int(rng.random() < 0.25), "re_pulse": int(rng.random() < 0.3), "addr": rng.getrandbits(32),
                      "wdata": rng.getrandbits(32), "rx_valid": int(rng.random() < 0.45), "rx_byte": rng.getrandbits(8), "tx_busy": int(rng.random() < 0.3),
                      "tx_done": int(rng.random() < 0.1), "tx_err": int(rng.random() < 0.5)})
        out.append(t)
    return out
