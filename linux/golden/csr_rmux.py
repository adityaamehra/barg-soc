"""Golden model of `csr_rmux`: the value a CSR reads, by its sel number. Combinational. Written by hand (iss_s.py csr_read)."""


def golden_csr_rmux(sel, mstatus, medeleg, mideleg, mie, mtvec, mcounteren, mscratch, mepc, mcause, mtval, mip, mcycle, minstret,
                    mtime, hartid, stvec, scounteren, sscratch, sepc, scause, stval, satp):
    M = 0xFFFFFFFF
    t = {1: mstatus, 2: 0x40141105, 3: medeleg, 4: mideleg, 5: mie, 6: mtvec, 7: mcounteren, 8: mscratch, 9: mepc, 10: mcause, 11: mtval,
         12: mip, 13: mcycle, 14: minstret, 15: mcycle >> 32, 16: minstret >> 32, 17: mcycle, 18: mtime, 19: minstret,
         20: mcycle >> 32, 21: mtime >> 32, 22: minstret >> 32, 23: 0, 24: 0, 25: 0, 26: hartid & 3, 27: mstatus & 0x000C0122,
         28: mie & mideleg, 29: stvec, 30: scounteren & 7, 31: sscratch, 32: sepc, 33: scause, 34: stval, 35: mip & mideleg, 36: satp}
    return {"rdata": t.get(sel & 63, 0) & M}


def vectors(rng):
    out = []
    for _ in range(5000):
        out.append({"sel": rng.randrange(40) if rng.random() < 0.95 else rng.randrange(64), "mstatus": rng.getrandbits(32),
                    "medeleg": rng.getrandbits(16), "mideleg": rng.getrandbits(12), "mie": rng.getrandbits(12), "mtvec": rng.getrandbits(32),
                    "mcounteren": rng.getrandbits(3), "mscratch": rng.getrandbits(32), "mepc": rng.getrandbits(32),
                    "mcause": rng.getrandbits(32), "mtval": rng.getrandbits(32), "mip": rng.getrandbits(12), "mcycle": rng.getrandbits(64),
                    "minstret": rng.getrandbits(64), "mtime": rng.getrandbits(64), "hartid": rng.getrandbits(2),
                    "stvec": rng.getrandbits(32), "scounteren": rng.getrandbits(3), "sscratch": rng.getrandbits(32),
                    "sepc": rng.getrandbits(32), "scause": rng.getrandbits(32), "stval": rng.getrandbits(32), "satp": rng.getrandbits(32)})
    return out
