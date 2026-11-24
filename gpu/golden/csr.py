"""Golden model of the CSR read unit (block `csr`). Combinational.

Lane l of y gets the value of CSR csr_addr for that lane: 0xCC0 tid = l; 0xCC1 wid; 0xCC2 cid = 0; 0xCC3 tmask; 0xCC4 gtid =
wid * 4 + l; 0xCC5 karg; 0xFC0 nt = 4; 0xFC1 nw = 4; 0xFC2 nc = 1; 0xC00 cycle and 0xC02 instret = cycle bits 31:0;
0xC80 cycleh and 0xC82 instreth = cycle bits 47:32 (the counter is 48 bits). Any other address: y = 0, and err = 1 when valid is 1 and unit is CSR (6).
"""

M = 0xFFFFFFFF


def golden_csr(csr_addr, valid, unit, wid, tmask, karg, cycle):
    lo, hi = cycle & M, cycle >> 32 & M
    fixed = {0xCC1: wid & 3, 0xCC2: 0, 0xCC3: tmask & 15, 0xCC5: karg & M, 0xFC0: 4, 0xFC1: 4, 0xFC2: 1,
             0xC00: lo, 0xC02: lo, 0xC80: hi, 0xC82: hi}
    y, known = 0, csr_addr in fixed or csr_addr in (0xCC0, 0xCC4)
    for l in range(4):
        if csr_addr == 0xCC0:
            v = l
        elif csr_addr == 0xCC4:
            v = (wid & 3) * 4 + l
        else:
            v = fixed.get(csr_addr, 0)
        y |= v << 32 * l
    return {"y": y, "err": int(bool(valid & 1) and unit == 6 and not known)}


def vectors(rng):
    """Directed vectors: every CSR address that exists (and some that do not), every warp and mask, valid CSR instructions
    and others. Random 12-bit addresses hit the thirteen real ones rarely."""
    real = [0xCC0, 0xCC1, 0xCC2, 0xCC3, 0xCC4, 0xCC5, 0xFC0, 0xFC1, 0xFC2, 0xC00, 0xC02, 0xC80, 0xC82]
    out = []
    for _ in range(1500):
        out.append({"csr_addr": rng.choice(real) if rng.random() < 0.8 else rng.randrange(4096),
                    "valid": 1 if rng.random() < 0.9 else 0, "unit": 6 if rng.random() < 0.9 else rng.randrange(8),
                    "wid": rng.randrange(4), "tmask": rng.randrange(16), "karg": rng.getrandbits(32),
                    "cycle": rng.choice((0, 1, 0xFFFFFFFF, 0x1_0000_0000, rng.getrandbits(48)))})
    return out
