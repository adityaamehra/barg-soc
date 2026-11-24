"""Golden model of `fp_hazard`. Combinational. Written by hand."""
WRITERS = (0x07, 0x43, 0x47, 0x4B, 0x4F, 0x53)


def golden_fp_hazard(stall, flush_id_ex, md_stall, dw_hold, id_valid, id_is_fp, half2, ex_valid, ex_inst, mem_valid, mem_inst):
    ex_wr = bool(ex_valid) and (ex_inst & 0x7F) in WRITERS
    mem_wr = bool(mem_valid) and (mem_inst & 0x7F) in WRITERS
    wait = bool(id_valid) and bool(id_is_fp) and not half2 and (ex_wr or mem_wr)
    return {"stall_out": int(bool(stall) or bool(dw_hold) or wait), "flush_out": int(bool(flush_id_ex) or (wait and not md_stall))}


def vectors(rng):
    v = []
    for _ in range(3000):
        def w():
            x = rng.getrandbits(32)
            return (x & ~0x7F) | rng.choice(WRITERS + (0x03, 0x27, 0x33, 0x53)) if rng.random() < 0.8 else x
        v.append({"stall": rng.getrandbits(1), "flush_id_ex": rng.getrandbits(1), "md_stall": rng.getrandbits(1), "dw_hold": rng.getrandbits(1),
                  "id_valid": int(rng.random() < 0.8), "id_is_fp": int(rng.random() < 0.7), "half2": rng.getrandbits(1),
                  "ex_valid": int(rng.random() < 0.7), "ex_inst": w(), "mem_valid": int(rng.random() < 0.7), "mem_inst": w()})
    return v
