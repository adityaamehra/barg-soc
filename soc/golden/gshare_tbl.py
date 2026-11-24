"""Golden model of `gshare_tbl`: gshare direction predictor (8-bit history, 256 two-bit counters) and a 32-entry branch target buffer. Clocked. Written by hand."""
M32 = 0xFFFFFFFF


def golden_gshare_tbl(trace):
    st = None
    out = []
    for i in trace:
        if st is None:
            out.append({k: None for k in ("pred_taken", "pred_redirect", "pred_target", "pred_idx")})
        else:
            ghr, pht, btb = st
            pc = i["pc"] & M32
            idx = ((pc >> 1) & 0xFF) ^ ghr
            bi = (pc >> 1) & 31
            e = btb[bi]
            hit = e is not None and e[0] == (pc >> 6)
            taken = int(hit and (e[2] or (pht[idx] >> 1)))
            out.append({"pred_taken": taken, "pred_redirect": int(taken and not (i["stall"] & 1)), "pred_target": e[1] if hit else 0, "pred_idx": idx})
        if i["rst"] & 1:
            st = (0, [1] * 256, [None] * 32)
        elif st is not None and (i["upd_en"] & 1):
            ghr, pht, btb = st
            taken = i["upd_taken"] & 1
            if i["upd_cond"] & 1:
                c = pht[i["upd_idx"] & 0xFF]
                pht[i["upd_idx"] & 0xFF] = min(3, c + 1) if taken else max(0, c - 1)
                ghr = ((ghr << 1) & 0xFF) | taken
            if taken:
                pc = i["upd_pc"] & M32
                btb[(pc >> 1) & 31] = (pc >> 6, i["upd_target"] & M32, i["upd_jump"] & 1)
            st = (ghr, pht, btb)
    return out


def traces(rng):
    out = []
    for _ in range(50):
        t = [{"rst": 1, "pc": 0, "stall": 0, "upd_en": 0, "upd_idx": 0, "upd_taken": 0, "upd_cond": 0, "upd_jump": 0, "upd_pc": 0, "upd_target": 0}]
        pcs = [rng.getrandbits(32) & ~1 for _ in range(6)]       # few distinct addresses so that entries are reused, hit and alias
        for _ in range(220):
            pc = rng.choice(pcs) if rng.random() < 0.8 else rng.getrandbits(32) & ~1
            upc = rng.choice(pcs) if rng.random() < 0.8 else rng.getrandbits(32) & ~1
            t.append({"rst": int(rng.random() < 0.004), "pc": pc, "stall": int(rng.random() < 0.2), "upd_en": int(rng.random() < 0.5),
                      "upd_idx": rng.getrandbits(8) if rng.random() < 0.5 else rng.randrange(4), "upd_taken": int(rng.random() < 0.6),
                      "upd_cond": int(rng.random() < 0.7), "upd_jump": int(rng.random() < 0.3), "upd_pc": upc, "upd_target": rng.getrandbits(32)})
        out.append(t)
    return out
