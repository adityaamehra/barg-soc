"""Golden model of `fp_exdec`: execute-stage decode of FP instructions into the FPU's operation. Combinational. Written by hand."""
FUSED = {0x43: 5, 0x47: 6, 0x4B: 7, 0x4F: 8}
RM_F5 = (0, 1, 2, 3, 0x0B, 8, 0x18, 0x1A)


def golden_fp_exdec(inst, valid, xcpt, frm):
    opc, f3, fmt, f5, rs2 = inst & 0x7F, inst >> 12 & 7, inst >> 25 & 3, inst >> 27, inst >> 20 & 31
    active = bool(valid) and not xcpt
    is_fpu = active and opc in (0x43, 0x47, 0x4B, 0x4F, 0x53)
    is_fst = active and opc == 0x27
    int_dest = is_fpu and opc == 0x53 and f5 in (0x14, 0x18, 0x1C)
    op = 0
    if opc in FUSED:
        op = FUSED[opc]
    elif opc == 0x53:
        op = {0: 0, 1: 1, 2: 2, 3: 3, 0x0B: 4, 4: 9 + f3, 5: 12 + f3, 8: 22 if fmt == 0 else 23, 0x14: 14 if f3 == 2 else 15 if f3 == 1 else 16,
              0x18: 18 + (rs2 & 1), 0x1A: 20 + (rs2 & 1), 0x1C: 17 if f3 == 1 else 24, 0x1E: 25}.get(f5, 0)
    dbl = (inst >> 25) & 1
    if opc == 0x53 and f5 == 8:
        dbl = 0
    has_rm = opc in FUSED or (opc == 0x53 and f5 in RM_F5)
    rm = (frm if f3 == 7 else f3) if has_rm else 0
    return {"is_fpu": int(is_fpu), "is_fst": int(is_fst), "int_dest": int(int_dest), "op": op & 31, "dbl": dbl, "rm": rm,
            "ra1": inst >> 15 & 31, "ra2": inst >> 20 & 31, "ra3": inst >> 27}


def vectors(rng):
    v = []
    ops = (0x07, 0x27, 0x43, 0x47, 0x4B, 0x4F, 0x53, 0x33)
    f5s = (0, 1, 2, 3, 4, 5, 8, 0x0B, 0x14, 0x18, 0x1A, 0x1C, 0x1E, 0x10, 0x1F)
    for _ in range(4000):
        w = rng.getrandbits(32)
        if rng.random() < 0.9:
            w = (w & ~0x7F) | rng.choice(ops)
            if rng.random() < 0.85:
                w = (w & ~(31 << 27)) | rng.choice(f5s) << 27
            if rng.random() < 0.7:
                w = (w & ~(7 << 12)) | rng.choice((0, 1, 2, 3, 4, 7)) << 12
        v.append({"inst": w, "valid": int(rng.random() < 0.85), "xcpt": int(rng.random() < 0.15), "frm": rng.choice((0, 1, 2, 3, 4, 4))})
    return v
