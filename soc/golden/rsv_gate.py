"""Golden model of the reservation gate of one core (block `rsv_gate`). Combinational. Written by hand."""


def golden_rsv_gate(set_rsv, clr_rsv, self_grant, snoop_we, addr, rsv_valid, rsv_addr):
    g = bool(self_grant & 1)
    other = bool(snoop_we & 1) and not g and bool(rsv_valid & 1) and (addr & 0xFFFFFFFF) >> 2 == (rsv_addr & 0xFFFFFFFF) >> 2
    return {"set": int(bool(set_rsv & 1) and g), "clear": int((bool(clr_rsv & 1) and g) or other)}


def vectors(rng):
    out = []
    for _ in range(3000):
        a = rng.getrandbits(32)
        out.append({"set_rsv": rng.getrandbits(1), "clr_rsv": rng.getrandbits(1), "self_grant": rng.getrandbits(1),
                    "snoop_we": rng.getrandbits(1), "addr": a, "rsv_valid": rng.getrandbits(1),
                    "rsv_addr": a if rng.random() < 0.5 else (a ^ rng.choice([1, 2, 3, 4, 0x100, 1 << 31]))})
    return out
