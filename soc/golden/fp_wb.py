"""Golden model of `fp_wb`: what a retiring FP instruction writes. Combinational. Written by hand."""
OPS = (0x43, 0x47, 0x4B, 0x4F, 0x53)


def golden_fp_wb(inst, commit, dwsel, mem_rdata, fres, flags, wrf):
    opc = inst & 0x7F
    is_load = bool(commit) and opc == 0x07
    is_op = bool(commit) and opc in OPS
    we_lo = (is_load and dwsel != 2) or (is_op and bool(wrf))
    we_hi = (is_load and dwsel != 1) or (is_op and bool(wrf))
    if is_load:
        lo, hi = mem_rdata, (mem_rdata if dwsel == 2 else 0xFFFFFFFF)
    else:
        lo, hi = fres & 0xFFFFFFFF, fres >> 32
    return {"we_lo": int(we_lo), "we_hi": int(we_hi), "waddr": inst >> 7 & 31, "wdata_lo": lo, "wdata_hi": hi,
            "flags_set": flags if is_op else 0, "dirty_set": int(is_load or (is_op and (bool(wrf) or flags != 0)))}


def vectors(rng):
    v = []
    for _ in range(3000):
        v.append({"inst": (rng.getrandbits(32) & ~0x7F) | rng.choice((0x07, 0x27, 0x43, 0x47, 0x4B, 0x4F, 0x53, 0x33, 0x03)),
                  "commit": int(rng.random() < 0.8), "dwsel": rng.choice((0, 1, 2)), "mem_rdata": rng.getrandbits(32), "fres": rng.getrandbits(64),
                  "flags": rng.choice((0, 0, rng.getrandbits(5))), "wrf": rng.getrandbits(1)})
    return v
