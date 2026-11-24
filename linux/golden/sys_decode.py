"""Golden model of the system-instruction decoder of the core with S-mode (`sys_decode`, regenerated). Combinational. Written by hand.

As the stage-4 decoder (demos/nuttx-soc/golden-a-16mb/sys_decode.py), plus: sret (10200073) is legal with csrop 101; sfence.vma
(funct7 0001001, rd 0, funct3 000, opcode 1110011, any rs1 and rs2) is legal with csrop 110; fence.i (opcode 0001111, funct3 001) has
csrop 111; the reserved fetch-fault words (opcode 0001011, funct3 001 or 010) raise cause 12 (instruction page fault) or 1
(instruction access fault), any other custom-0 word is illegal; ecall raises 8 + priv (8 user, 9 supervisor, 11 machine; priv 2 as 3).
csrop codes: 0 none, 1 read, 2 write, 3 set, 4 clear, 5 sret, 6 sfence.vma, 7 fence.i."""

ECALL, EBREAK, MRET, SRET, WFI = 0x00000073, 0x00100073, 0x30200073, 0x10200073, 0x10500073
AMO_OPS = {2: 1, 3: 2, 1: 3, 0: 4, 4: 5, 12: 6, 8: 7, 16: 8, 20: 9, 24: 10, 28: 11}


def _is_sfence(w):
    return w & 0x7F == 0x73 and (w >> 25) == 0x09 and (w >> 12 & 7) == 0 and (w >> 7 & 31) == 0


def _legal(w):
    if w & 3 != 3:
        return False
    op, f3, f7 = w & 0x7F, (w >> 12) & 7, w >> 25
    if op in (0x37, 0x17, 0x6F):
        return True
    if op == 0x67:
        return f3 == 0
    if op == 0x63:
        return f3 in (0, 1, 4, 5, 6, 7)
    if op == 0x03:
        return f3 in (0, 1, 2, 4, 5)
    if op == 0x23:
        return f3 in (0, 1, 2)
    if op == 0x13:
        if f3 == 1:
            return f7 == 0
        if f3 == 5:
            return f7 in (0, 0x20)
        return True
    if op == 0x33:
        return f7 in (0, 1) or (f7 == 0x20 and f3 in (0, 5))
    if op == 0x0F:
        return f3 in (0, 1)
    if op == 0x2F:
        f5 = w >> 27
        if f3 != 2:
            return False
        return f5 in (0, 1, 3, 4, 8, 12, 16, 20, 24, 28) or (f5 == 2 and (w >> 20) & 31 == 0)
    if op == 0x73:
        return (w in (ECALL, EBREAK, MRET, SRET, WFI) or _is_sfence(w)) if f3 == 0 else f3 != 4
    if op == 0x0B:
        return f3 in (1, 2)
    return False


def golden_sys_decode(inst, priv):
    w = inst & 0xFFFFFFFF
    out = {"xcpt": 0, "cause": 0, "csrop": 0, "csr_imm": 0, "is_csr": 0, "is_mret": int(w == MRET), "is_amo": 0, "amo_op": 0}
    if w & 0x7F == 0x2F and _legal(w):
        out.update(is_amo=1, amo_op=AMO_OPS[w >> 27])
    if not _legal(w):
        out.update(xcpt=1, cause=2)
    elif w & 0x7F == 0x0B:
        out.update(xcpt=1, cause=12 if (w >> 12 & 7) == 1 else 1)
    elif w == EBREAK:
        out.update(xcpt=1, cause=3)
    elif w == ECALL:
        out.update(xcpt=1, cause={0: 8, 1: 9}.get(priv & 3, 11))
    elif w == SRET:
        out.update(csrop=5)
    elif _is_sfence(w):
        out.update(csrop=6)
    elif w & 0x7F == 0x0F and (w >> 12 & 7) == 1:
        out.update(csrop=7)
    elif w & 0x7F == 0x73 and (w >> 12) & 7 != 0:
        f3, src = (w >> 12) & 7, (w >> 15) & 31
        kind = f3 & 3
        csrop = 2 if kind == 1 else (3 if kind == 2 else 4) if src else 1
        out.update(is_csr=1, csr_imm=f3 >> 2, csrop=csrop)
    return out


def vectors(rng):
    out = [{"inst": rng.getrandbits(32), "priv": rng.choice([0, 1, 2, 3])} for _ in range(800)]
    for f5 in range(32):
        for aq in range(4):
            for f3 in (2, 2, rng.randrange(8)):
                out.append({"inst": (f5 << 27) | (aq << 25) | (rng.getrandbits(5) << 20) | (rng.getrandbits(5) << 15) | (f3 << 12)
                            | (rng.getrandbits(5) << 7) | 0x2F, "priv": 3})
    for rs2 in range(32):
        out.append({"inst": (2 << 27) | (rs2 << 20) | (2 << 12) | 0x2F, "priv": 1})
    for w in (ECALL, EBREAK, MRET, SRET, WFI, 0x00200073, 0x10200073 | 1 << 7, 0x7B200073):
        for p in range(4):
            out.append({"inst": w, "priv": p})
    for _ in range(300):                                # sfence.vma and near misses
        w = 0x12000073 | rng.getrandbits(5) << 15 | rng.getrandbits(5) << 20
        if rng.random() < 0.3:
            w ^= rng.choice([1 << 7, 1 << 12, 1 << 25, 1 << 31, 1 << 13])
        out.append({"inst": w, "priv": rng.choice([0, 1, 3])})
    for f3 in range(8):                                 # fence / fence.i / custom-0 fault words
        for _ in range(8):
            out.append({"inst": (rng.getrandbits(17) << 15) | (f3 << 12) | (rng.getrandbits(5) << 7) | 0x0F, "priv": 1})
            out.append({"inst": (rng.getrandbits(1) << 20) | (f3 << 12) | 0x0B, "priv": 1})
            out.append({"inst": (rng.getrandbits(17) << 15) | (f3 << 12) | (rng.getrandbits(5) << 7) | 0x0B, "priv": 0})
    for f3 in range(8):
        for src in (0, 1, 31):
            out.append({"inst": (rng.getrandbits(12) << 20) | (src << 15) | (f3 << 12) | (rng.getrandbits(5) << 7) | 0x73, "priv": 1})
    return out
