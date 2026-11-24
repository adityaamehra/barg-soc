"""Golden model of the 16550-style UART with a 16-byte receive FIFO (block `uart16550f`). Clocked. Written by hand, as an extension of the
one-byte-buffer model of demos/nuttx-soc: the same registers and the same transmitter; the receive buffer becomes a 16-byte FIFO with an
overrun flag in the line status register (bit 1, cleared by reading it) and a FIFO reset by the FIFO control register (bit 1).
Outputs are what the block shows before the edge; before the first reset they are None."""

FRESH = {"ier": 0, "lcr": 0, "mcr": 0, "scr": 0, "dll": 0, "dlm": 0, "fe": 0, "txf": 0, "oe": 0, "mem": [0] * 16, "rp": 0, "wp": 0, "cnt": 0}


def _iir(s):
    rx = bool(s["ier"] & 1 and s["cnt"] != 0)
    tx = bool(s["ier"] & 2 and s["txf"])
    ident = 0b010 if rx else 0b001 if tx else 0
    return (0 if (rx or tx) else 1) | (ident << 1) | (0xC0 if s["fe"] else 0), rx, tx


def golden_uart16550f(trace):
    s = None
    out = []
    for step in trace:
        off = step["addr"] & 7
        if s is None:
            out.append({"rdata": None, "irq": None, "tx_valid": None, "tx_data": None})
        else:
            dlab = s["lcr"] >> 7 & 1
            iir, rx, tx = _iir(s)
            front = s["mem"][s["rp"]] if s["cnt"] else 0
            rdata = {0: s["dll"] if dlab else front, 1: s["dlm"] if dlab else s["ier"] & 15, 2: iir, 3: s["lcr"], 4: s["mcr"] & 31,
                     5: (1 if s["cnt"] else 0) | s["oe"] << 1 | 0x60, 6: 0, 7: s["scr"]}[off]
            send = bool(step["we"] & 1 and off == 0 and not dlab)
            out.append({"rdata": rdata, "irq": int(rx or tx), "tx_valid": int(send), "tx_data": step["wdata"] & 0xFF if send else 0})
        if step["rst"] & 1:
            s = {**FRESH, "mem": [0] * 16}
        elif s is not None:
            dlab = s["lcr"] >> 7 & 1
            we, re = step["we"] & 1, step["re"] & 1
            iir, _, _ = _iir(s)
            w = step["wdata"] & 0xFF
            if re and off == 0 and not dlab and s["cnt"]:
                s["rp"] = (s["rp"] + 1) % 16
                s["cnt"] -= 1
            if re and off == 5:
                s["oe"] = 0
            if re and off == 2 and (iir >> 1) & 7 == 1:
                s["txf"] = 0
            if we:
                if off == 0:
                    if dlab:
                        s["dll"] = w
                    else:
                        s["txf"] = 1
                elif off == 1:
                    if dlab:
                        s["dlm"] = w
                    else:
                        if not s["ier"] & 2 and w & 2:
                            s["txf"] = 1
                        s["ier"] = w & 15
                elif off == 2:
                    s["fe"] = w & 1
                    if w & 2:
                        s["rp"] = s["wp"] = s["cnt"] = 0
                elif off == 3:
                    s["lcr"] = w
                elif off == 4:
                    s["mcr"] = w & 31
                elif off == 7:
                    s["scr"] = w
            if step["rx_valid"] & 1:
                if s["cnt"] < 16:
                    s["mem"][s["wp"]] = step["rx_data"] & 0xFF
                    s["wp"] = (s["wp"] + 1) % 16
                    s["cnt"] += 1
                else:
                    s["oe"] = 1
    return out


def traces(rng=None, count=60, length=420):
    """Traces over all eight registers with the divisor latch on and off; bursts of received bytes that fill the FIFO, reads that drain it, FIFO resets."""
    import random
    rng = rng or random.Random(5)
    result = []
    for _ in range(count):
        trace = [{"rst": 1, "addr": 0, "wdata": 0, "we": 0, "re": 0, "rx_valid": 0, "rx_data": 0}]
        rx_p = rng.choice([0.1, 0.3, 0.6])       # how busy the receiver is in this trace
        rd_p = rng.choice([0.1, 0.3, 0.5])       # how often the data register is read
        while len(trace) < length:
            off = rng.choice([0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 5, 5, 6, 7])
            write = rng.random() < 0.3
            read = not write and rng.random() < (rd_p if off == 0 else 0.7)
            if off == 3 and write:
                wdata = rng.choice([0x03, 0x83, 0x80, 0x00, rng.getrandbits(8)])
            elif off == 1 and write:
                wdata = rng.choice([0, 1, 2, 3, 15, rng.getrandbits(8)])
            elif off == 2 and write:
                wdata = rng.choice([0, 1, 3, 7, 0xC7, 0x02, rng.getrandbits(8)])
            else:
                wdata = rng.getrandbits(8) | (rng.getrandbits(24) << 8 if rng.random() < 0.2 else 0)
            trace.append({"rst": int(rng.random() < 0.004), "addr": 0x10000000 | off | rng.choice([0, 8, 0x100]), "wdata": wdata,
                          "we": int(write), "re": int(read), "rx_valid": int(rng.random() < rx_p), "rx_data": rng.getrandbits(8)})
        result.append(trace)
    return result
