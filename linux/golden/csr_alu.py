"""Golden model of `csr_alu`: the value a CSR instruction writes. Combinational. Written by hand."""


def golden_csr_alu(old, src, csrop):
    op = csrop & 7
    old &= 0xFFFFFFFF
    src &= 0xFFFFFFFF
    new = src if op == 2 else (old | src) if op == 3 else (old & ~src & 0xFFFFFFFF) if op == 4 else old
    return {"nval": new}


def vectors(rng):
    return [{"old": rng.getrandbits(32), "src": rng.getrandbits(32), "csrop": rng.randrange(8)} for _ in range(3000)]
