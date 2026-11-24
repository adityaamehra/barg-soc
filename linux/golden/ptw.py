"""Golden model of `ptw`: the Sv32 page-table walker. Clocked (free clock). Written by hand from iss_s.py's translate.

States IDLE, L1, L0. A PTE address a is 34 bits; it is in RAM when a bits 33:26 are 00100000 (0x8000_0000..0x83FF_FFFF)."""

M32 = 0xFFFFFFFF


class Ptw:
    def __init__(self):
        self.s = None

    def outputs(self, i):
        if self.s is None:
            return {k: None for k in ("busy", "req", "addr", "fill", "fill_vpn", "fill_ppn", "fill_mega", "fill_flags", "fault",
                                      "fault_access", "fault_vpn")}
        s = self.s
        o = {"busy": int(s["st"] != 0), "req": 0, "addr": 0, "fill": 0, "fill_vpn": 0, "fill_ppn": 0, "fill_mega": 0, "fill_flags": 0,
             "fault": s["fault"], "fault_access": s["facc"], "fault_vpn": s["fvpn"]}
        if s["st"] in (1, 2):
            inram = s["a"] >> 26 == 0b00100000
            o["req"], o["addr"] = int(inram), (s["a"] & M32) if inram else 0
            if inram and i["grant"] & 1:
                pte = i["rdata"] & M32
                v, r, w, x = pte & 1, pte >> 1 & 1, pte >> 2 & 1, pte >> 3 & 1
                ppn = pte >> 10 & 0x3FFFFF
                if v and not (not r and w) and (r or x) and not (s["st"] == 1 and ppn & 0x3FF):
                    o.update(fill=1, fill_vpn=s["va"] >> 12 & 0xFFFFF, fill_ppn=ppn, fill_mega=int(s["st"] == 1), fill_flags=pte & 0xFF)
        return o

    def edge(self, i):
        if i["rst"] & 1:
            self.s = {"st": 0, "a": 0, "va": 0, "fault": 0, "facc": 0, "fvpn": 0}
            return
        s = self.s
        if s is None:
            return
        if i["clear"] & 1:
            s["fault"] = 0
            s["st"] = 0
            return
        if s["st"] == 0:
            if i["start"] & 1:
                va = i["vaddr"] & M32
                s.update(st=1, va=va, a=((i["satp_ppn"] & 0x3FFFFF) << 12) + (va >> 22) * 4, fault=0)
            return
        inram = s["a"] >> 26 == 0b00100000
        if not inram or (i["deny"] & 1):
            s.update(st=0, fault=1, facc=1, fvpn=s["va"] >> 12)
            return
        if not i["grant"] & 1:
            return
        pte = i["rdata"] & M32
        v, r, w, x = pte & 1, pte >> 1 & 1, pte >> 2 & 1, pte >> 3 & 1
        ppn = pte >> 10 & 0x3FFFFF
        if not v or (not r and w):
            s.update(st=0, fault=1, facc=0, fvpn=s["va"] >> 12)
        elif r or x:
            if s["st"] == 1 and ppn & 0x3FF:
                s.update(st=0, fault=1, facc=0, fvpn=s["va"] >> 12)
            else:
                s.update(st=0)
        elif s["st"] == 2 or pte & 0xD0:   # a pointer at L0, or a pointer with D, A or U set (reserved)
            s.update(st=0, fault=1, facc=0, fvpn=s["va"] >> 12)
        else:
            s.update(st=2, a=(ppn << 12) + (s["va"] >> 12 & 0x3FF) * 4)


def golden_ptw(trace):
    m, out = Ptw(), []
    for st in trace:
        out.append(m.outputs(st))
        m.edge(st)
    return out


def traces(rng):
    def pte():
        r = rng.random()
        ppn = rng.choice([0x80000 + rng.getrandbits(14), 0x80000 + (rng.getrandbits(4) << 10), rng.getrandbits(22)])
        if r < 0.35:
            flags = 0x01                                      # pointer
        elif r < 0.75:
            flags = 0x01 | rng.choice([0x2, 0x6, 0xA, 0xE, 0x8]) | rng.getrandbits(1) << 4 | rng.getrandbits(2) << 6
        else:
            flags = rng.getrandbits(8)
        return ppn << 10 | rng.getrandbits(2) << 8 | flags
    out = []
    for _ in range(60):
        t = [{"rst": 1, "start": 0, "vaddr": 0, "satp_ppn": 0, "grant": 0, "rdata": 0, "clear": 0, "deny": 0}]
        satp = rng.choice([0x80000 + rng.getrandbits(14), rng.getrandbits(22)])
        for _ in range(100):
            t.append({"rst": int(rng.random() < 0.005), "start": int(rng.random() < 0.3), "vaddr": rng.getrandbits(32), "satp_ppn": satp,
                      "grant": int(rng.random() < 0.7), "rdata": pte(), "clear": int(rng.random() < 0.1), "deny": int(rng.random() < 0.08)})
        out.append(t)
    return out
