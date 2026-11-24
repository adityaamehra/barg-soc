"""Golden model of `fp_dec`: legality of the F and D instructions and the integer stand-in the integer decoder sees. Combinational. Written by hand."""


def rm_ok(f3, frm):
    return f3 <= 4 or (f3 == 7 and frm <= 4)


def legal(w, frm):
    op, f3, fmt, f5, rs2 = w & 0x7F, w >> 12 & 7, w >> 25 & 3, w >> 27, w >> 20 & 31
    ok = rm_ok(f3, frm)
    if op == 0x07 or op == 0x27:
        return f3 in (2, 3)
    if op in (0x43, 0x47, 0x4B, 0x4F):
        return fmt in (0, 1) and ok
    if op != 0x53 or fmt not in (0, 1):
        return False
    if f5 in (0, 1, 2, 3):
        return ok
    if f5 == 0x0B:
        return rs2 == 0 and ok
    if f5 == 4:
        return f3 in (0, 1, 2)
    if f5 == 5:
        return f3 in (0, 1)
    if f5 == 8:
        return ok and ((fmt == 0 and rs2 == 1) or (fmt == 1 and rs2 == 0))
    if f5 == 0x14:
        return f3 in (0, 1, 2)
    if f5 in (0x18, 0x1A):
        return rs2 in (0, 1) and ok
    if f5 == 0x1C:
        return rs2 == 0 and (f3 == 1 or (f3 == 0 and fmt == 0))
    if f5 == 0x1E:
        return rs2 == 0 and f3 == 0 and fmt == 0
    return False


def golden_fp_dec(inst, fs, frm):
    op, f3, f5 = inst & 0x7F, inst >> 12 & 7, inst >> 27
    is_fp = int(legal(inst, frm) and fs != 0)
    is_dw = int(bool(is_fp) and op in (0x07, 0x27) and f3 == 3)
    if not is_fp:
        d = inst
    elif op == 0x07:
        d = (inst >> 15) << 15 | 2 << 12 | 0x03
    elif op == 0x27:
        d = (inst & ~0x707F) | 2 << 12 | 0x23
    else:
        rd = inst >> 7 & 31 if (op == 0x53 and f5 in (0x14, 0x18, 0x1C)) else 0
        d = (inst >> 20 & 31) << 20 | (inst >> 15 & 31) << 15 | rd << 7 | 0x33
    return {"is_fp": is_fp, "is_dw": is_dw, "dec_inst": d}


def vectors(rng):
    v = []
    ops = (0x07, 0x27, 0x43, 0x47, 0x4B, 0x4F, 0x53)
    f5s = (0, 1, 2, 3, 4, 5, 8, 0x0B, 0x14, 0x18, 0x1A, 0x1C, 0x1E)
    for _ in range(4000):
        w = rng.getrandbits(32)
        if rng.random() < 0.9:
            op = rng.choice(ops)
            w = (w & ~0x7F) | op
            if op == 0x53 and rng.random() < 0.9:
                w = (w & ~(31 << 27)) | rng.choice(f5s) << 27
                w &= ~(2 << 25) if rng.random() < 0.9 else 0xFFFFFFFF
            if rng.random() < 0.7:
                w = (w & ~(7 << 12)) | rng.choice((0, 1, 2, 3, 4, 7)) << 12
            if rng.random() < 0.5:
                w &= ~(31 << 20) if rng.random() < 0.5 else ~(30 << 20)
        v.append({"inst": w, "fs": rng.choice((0, 1, 2, 3, 3, 3)), "frm": rng.choice((0, 1, 2, 3, 4, 5, 6, 7))})
    return v
