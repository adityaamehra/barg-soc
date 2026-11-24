"""Golden model of `trap_unit`: what the write-back stage does with its instruction. Combinational. Written by hand from iss_s.py.
csrop: 0 none, 1 CSR read, 2 CSR write, 3 CSR set, 4 CSR clear, 5 sret, 6 sfence.vma, 7 fence.i."""


def golden_trap_unit(valid, xcpt, irq, cause, pc, tval, inst, csrop, is_mret, illegal_csr, priv, tsr, tvm, medeleg, mideleg,
                     mtvec, stvec, mepc, sepc):
    M = 0xFFFFFFFF
    op, priv = csrop & 7, priv & 3
    v = bool(valid & 1)
    illegal = bool(illegal_csr & 1) or (bool(is_mret & 1) and priv != 3) or (op == 5 and (priv == 0 or (priv == 1 and tsr & 1))) \
        or (op == 6 and (priv == 0 or (priv == 1 and tvm & 1)))
    trap = v and (bool(xcpt & 1) or illegal)
    c = (cause & 15) if xcpt & 1 else 2
    is_int = bool(xcpt & 1) and bool(irq & 1)
    t = (0 if is_int else tval & M) if xcpt & 1 else inst & M
    deleg = priv != 3 and bool(((mideleg if is_int else medeleg) >> c) & 1)
    trap_s, trap_m = trap and deleg, trap and not deleg
    mret = v and not trap and bool(is_mret & 1)
    sret = v and not trap and op == 5
    csr_we = v and not trap and op in (2, 3, 4)
    sfence = v and not trap and op == 6
    refetch = v and not trap and op in (2, 3, 4, 6, 7)

    def vec(base):
        return ((base & ~3) + (4 * c if is_int and base & 1 else 0)) & M
    rpc = vec(mtvec) if trap_m else vec(stvec) if trap_s else (mepc & M) if mret else (sepc & M) if sret else (pc + 4) & M
    return {"redirect": int(trap or mret or sret or refetch), "kill": int(trap or mret or sret), "redirect_pc": rpc, "trap_m": int(trap_m), "trap_s": int(trap_s),
            "mret": int(mret), "sret": int(sret), "csr_we": int(csr_we), "sfence": int(sfence), "retire": int(v and not trap),
            "epc": pc & M & ~1, "cause_val": (1 << 31 if is_int else 0) | c, "tval_out": t}


def vectors(rng):
    out = []
    for _ in range(6000):
        xc = int(rng.random() < 0.3)
        irq = int(xc and rng.random() < 0.4)
        cause = rng.choice([1, 3, 5, 7, 9, 11]) if irq else rng.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 15])
        out.append({"valid": int(rng.random() < 0.9), "xcpt": xc, "irq": irq,
                    "cause": cause,
                    "pc": rng.getrandbits(32), "tval": rng.getrandbits(32), "inst": rng.getrandbits(32), "csrop": rng.randrange(8),
                    "is_mret": int(rng.random() < 0.15), "illegal_csr": int(rng.random() < 0.15), "priv": rng.choice([0, 1, 3]),
                    "tsr": rng.getrandbits(1), "tvm": rng.getrandbits(1), "medeleg": rng.choice([0, 0xB109, rng.getrandbits(16)]),
                    "mideleg": rng.choice([0, 0x222, rng.getrandbits(12)]), "mtvec": rng.getrandbits(32), "stvec": rng.getrandbits(32),
                    "mepc": rng.getrandbits(32), "sepc": rng.getrandbits(32)})
    return out
