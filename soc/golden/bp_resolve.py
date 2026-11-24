"""Golden model of `bp_resolve`: compare the carried prediction with the branch unit's decision. Combinational. Written by hand."""
M32 = 0xFFFFFFFF


def golden_bp_resolve(pcsel, br_redirect, br_pc, valid, pc_plus4, pt, ptarget, pidx):
    actual = int(bool(valid) and bool(br_redirect))
    mis = bool(valid) and (pt != actual or (actual == 1 and ptarget != br_pc))
    return {"redirect": int(mis), "redirect_pc": br_pc if actual else pc_plus4, "upd_en": int(bool(valid) and pcsel != 0), "upd_idx": pidx, "upd_taken": actual,
            "upd_cond": int(pcsel == 1), "upd_jump": int(pcsel in (2, 3))}


def vectors(rng):
    v = []
    for _ in range(3000):
        tg = rng.getrandbits(32)
        v.append({"pcsel": rng.getrandbits(2), "br_redirect": rng.getrandbits(1), "br_pc": tg, "valid": int(rng.random() < 0.8), "pc_plus4": rng.getrandbits(32),
                  "pt": rng.getrandbits(1), "ptarget": tg if rng.random() < 0.6 else rng.getrandbits(32), "pidx": rng.getrandbits(8)})
    return v
