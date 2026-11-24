"""Golden model of `xlate_on`: is translation on for fetch and for data, and the data side's privilege. Combinational. Written by hand."""


def golden_xlate_on(priv, mprv, mpp, satp_mode):
    p = priv & 3
    dp = (mpp & 3) if (mprv & 1 and p == 3) else p
    return {"xlate_i": int(bool(satp_mode & 1) and p != 3), "xlate_d": int(bool(satp_mode & 1) and dp != 3), "dpriv": dp, "kind_i": 0}


def vectors(rng):
    return [{"priv": p, "mprv": a, "mpp": m, "satp_mode": s} for p in range(4) for a in range(2) for m in range(4) for s in range(2)] * 4
