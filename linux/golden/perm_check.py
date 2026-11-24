"""Golden model of `perm_check`: does an access fault on a leaf PTE's flags. Combinational. Written by hand (iss_s.py).
kind 0 fetch, 1 load, 2 store (3 as store); flags = PTE bits 7:0: V0 R1 W2 X3 U4 G5 A6 D7."""


def golden_perm_check(kind, priv, sum, mxr, flags):
    k, p = kind & 3, priv & 3
    r, w, x, u, a, d = (flags >> 1) & 1, (flags >> 2) & 1, (flags >> 3) & 1, (flags >> 4) & 1, (flags >> 6) & 1, (flags >> 7) & 1
    store = k >= 2
    if p == 3:
        return {"fault": 0}
    fault = (p == 0 and not u) or (p == 1 and u and (k == 0 or not sum & 1))
    ok = x if k == 0 else w if store else (r or (x and mxr & 1))
    fault = fault or not ok or not a or (store and not d)
    return {"fault": int(bool(fault))}


def vectors(rng):
    return [{"kind": rng.randrange(4), "priv": rng.choice([0, 1, 1, 3]), "sum": rng.getrandbits(1), "mxr": rng.getrandbits(1),
             "flags": rng.getrandbits(8) | (0xC1 if rng.random() < 0.5 else 0)} for _ in range(4000)]
