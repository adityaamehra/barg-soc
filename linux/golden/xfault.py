"""Golden model of `xfault`: the result of one translation lookup. Combinational. Written by hand."""


def golden_xfault(hit, perm_fault, wfault, waccess, wvpn, va):
    held = bool(wfault & 1) and (wvpn & 0xFFFFF) == (va >> 12 & 0xFFFFF)
    h = bool(hit & 1)
    return {"pf": int(bool(perm_fault & 1) if h else (held and not waccess & 1)), "af": int(not h and held and bool(waccess & 1)),
            "miss": int(not h and not held)}


def vectors(rng):
    out = []
    for _ in range(3000):
        v = rng.getrandbits(20)
        out.append({"hit": rng.getrandbits(1), "perm_fault": rng.getrandbits(1), "wfault": rng.getrandbits(1), "waccess": rng.getrandbits(1),
                    "wvpn": v if rng.random() < 0.5 else rng.getrandbits(20), "va": v << 12 | rng.getrandbits(12)})
    return out
