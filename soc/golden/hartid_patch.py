"""Golden model of the hart id patch of the CSR read path (block `hartid_patch`). Combinational. Written by hand."""


def golden_hartid_patch(csr_sel, rdata, hartid):
    return {"y": (hartid & 3) if csr_sel & 31 == 21 else rdata & 0xFFFFFFFF}


def vectors(rng):
    return [{"csr_sel": rng.choice([21, 21, 20, 22, 0, 18, rng.getrandbits(5)]), "rdata": rng.getrandbits(32), "hartid": rng.getrandbits(2)}
            for _ in range(1000)]
