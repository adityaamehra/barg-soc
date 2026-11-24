"""Golden model of the execute-stage exception unit of the core with an MMU (`ex_xcpt`, regenerated). Combinational. By hand.
As the stage-4 unit, plus: a decode exception with cause 12 or 1 (a fetch fault) has trap value pc, plus 2 when inst bit 20 is 1;
after a misaligned access, a data page fault (d_pf) raises 15 (d_store) or 13, a data access fault (d_af) 7 or 5, trap value alu_y."""

WORD = (2, 6, 7)


def golden_ex_xcpt(id_xcpt, id_cause, id_irq, inst, pc, memtype, memwrite, alu_y, d_pf, d_af, d_store):
    M = 0xFFFFFFFF
    memtype &= 7
    misaligned = (memtype in WORD and alu_y & 3 != 0) or (memtype in (1, 4) and alu_y & 1 != 0)
    if id_xcpt & 1:
        cause = id_cause & 15
        if id_irq & 1:
            tval = 0
        elif cause == 2:
            tval = inst & M
        elif cause == 3:
            tval = pc & M
        elif cause in (12, 1):
            tval = (pc + (2 if inst >> 20 & 1 else 0)) & M
        else:
            tval = 0
        xcpt = 1
    elif misaligned:
        xcpt, cause, tval = 1, 6 if d_store & 1 else 4, alu_y & M
    elif d_pf & 1:
        xcpt, cause, tval = 1, 15 if d_store & 1 else 13, alu_y & M
    elif d_af & 1:
        xcpt, cause, tval = 1, 7 if d_store & 1 else 5, alu_y & M
    else:
        xcpt, cause, tval = 0, 0, 0
    return {"xcpt": xcpt, "cause": cause, "tval": tval, "memwrite_out": int(bool(memwrite & 1 and not xcpt))}


def vectors(rng):
    out = []
    for _ in range(5000):
        ix = int(rng.random() < 0.3)
        out.append({"id_xcpt": ix, "id_cause": rng.choice([1, 2, 3, 8, 9, 11, 12, rng.getrandbits(4)]), "id_irq": int(ix and rng.random() < 0.3),
                    "inst": rng.getrandbits(32), "pc": rng.getrandbits(32), "memtype": rng.randrange(8), "memwrite": rng.getrandbits(1),
                    "alu_y": rng.getrandbits(32), "d_pf": int(rng.random() < 0.3), "d_af": int(rng.random() < 0.2),
                    "d_store": rng.getrandbits(1)})
    return out
