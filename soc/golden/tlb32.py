"""Golden model of `tlb32`: 32 fully associative entries, filled in turn, flushed all at once. Clocked. Written by hand.
flags are PTE bits 7:0 (V R W X U G A D). A megapage entry matches on vpn bits 19:10 and passes vpn bits 9:0 through."""


class Tlb:
    def __init__(self):
        self.e, self.ptr = None, 0

    def outputs(self, i):
        if self.e is None:
            return {"hit": None, "ppa": None, "flags": None}
        vpn = (i["va"] >> 12) & 0xFFFFF
        for valid, evpn, ppn, mega, flags in self.e:
            if valid and ((evpn >> 10 == vpn >> 10) if mega else evpn == vpn):
                ppa = ((ppn >> 10 & 0x3FF) << 10 | (vpn & 0x3FF)) if mega else ppn & 0xFFFFF
                return {"hit": 1, "ppa": ppa, "flags": flags}
        return {"hit": 0, "ppa": 0, "flags": 0}

    def edge(self, i):
        if i["rst"] & 1:
            self.e, self.ptr = [(0, 0, 0, 0, 0)] * 32, 0
            return
        if self.e is None:
            return
        if i["flush"] & 1:
            self.e, self.ptr = [(0, 0, 0, 0, 0)] * 32, 0
        elif i["fill"] & 1:
            self.e[self.ptr] = (1, i["fill_vpn"] & 0xFFFFF, i["fill_ppn"] & 0x3FFFFF, i["fill_mega"] & 1, i["fill_flags"] & 0xFF)
            self.ptr = (self.ptr + 1) & 31


def golden_tlb32(trace):
    m, out = Tlb(), []
    for s in trace:
        out.append(m.outputs(s))
        m.edge(s)
    return out


def traces(rng):
    out = []
    for _ in range(40):
        pool = [rng.getrandbits(20) for _ in range(40)]
        t = [{"rst": 1, "flush": 0, "fill": 0, "fill_vpn": 0, "fill_ppn": 0, "fill_mega": 0, "fill_flags": 0, "va": 0}]
        for _ in range(300):
            v = rng.choice(pool)
            t.append({"rst": int(rng.random() < 0.005), "flush": int(rng.random() < 0.03), "fill": int(rng.random() < 0.3),
                      "fill_vpn": rng.choice(pool), "fill_ppn": rng.getrandbits(22), "fill_mega": int(rng.random() < 0.3),
                      "fill_flags": rng.getrandbits(8), "va": ((v ^ (rng.getrandbits(10) if rng.random() < 0.2 else 0)) << 12) | rng.getrandbits(12)})
        out.append(t)
    return out
