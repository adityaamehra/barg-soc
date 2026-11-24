"""Golden model of the raster-output unit's pixel write (block `rop_unit`). Combinational. Never shown to the generator.

The pix instruction: act = valid & advance & gfx & (gfx_op == 5). For each lane l (lane l of a 128-bit bus is bits 32l+31..32l) with
tmask bit l set and act: position = lane l of a: x = bits 15:0, y = bits 31:16; colour = lane l of b, ARGB8888 (alpha ignored).
The lane draws when x < 320, y < 240 and sc_x0 <= x < sc_x1 and sc_y0 <= y < sc_y1 (the scissor box; sc_* are 9-bit values).
A drawing lane writes video memory bank k = x bits 1:0, at index y * 80 + (x >> 2), the value RGB565 = {r[7:3], g[7:2], b[7:3]}
with r = colour bits 23:16, g = 15:8, b = 7:0. When several drawing lanes are on one bank (same x mod 4) the highest-numbered
lane is the one written. Outputs per bank k (0..3): r_we<k> = 1 when some lane writes bank k, r_waddr<k> (15 bits) and r_wdata<k>
(16 bits) the index and RGB565 value; all of r_waddr<k> and r_wdata<k> are 0 when r_we<k> is 0.
G2c-2: r_raddr<k> is the index the winning lane of bank k would write, by the same rules but with pre = valid & gfx & (gfx_op == 5)
in place of act (advance not required: the read happens in the stall cycle); 0 when no lane draws on bank k. When blend is 1 the
written value is source-over: a = colour bits 31:24, the destination d = vw_rdata<k> widened (r8 = r5 << 3 | r5 >> 2, g8 = g6 << 2 |
g6 >> 4, b8 = b5 << 3 | b5 >> 2), per channel x = s * a + d * (255 - a), out = (x + 128 + ((x + 128) >> 8)) >> 8, then truncated to
RGB565 as in replace.
"""

M = 0xFFFFFFFF


def golden_rop_unit(valid, advance, gfx, gfx_op, tmask, a, b, sc_x0, sc_y0, sc_x1, sc_y1, blend, vw_rdata0, vw_rdata1, vw_rdata2,
                    vw_rdata3):
    out = {}
    for k in range(4):
        out[f"r_we{k}"] = out[f"r_waddr{k}"] = out[f"r_wdata{k}"] = out[f"r_raddr{k}"] = 0
    if not (valid & 1 and gfx & 1 and gfx_op & 7 == 5):
        return out
    rd = [vw_rdata0, vw_rdata1, vw_rdata2, vw_rdata3]
    act = advance & 1
    for l in range(4):
        if not tmask >> l & 1:
            continue
        pos, col = a >> 32 * l & M, b >> 32 * l & M
        x, y = pos & 0xFFFF, pos >> 16
        if x < 320 and y < 240 and sc_x0 <= x < sc_x1 and sc_y0 <= y < sc_y1:
            k = x & 3
            out[f"r_raddr{k}"] = y * 80 + (x >> 2)
            if not act:
                continue
            if blend & 1:
                al, d = col >> 24 & 255, rd[k] & 0xFFFF
                dd = ((d >> 11 & 31) << 3 | (d >> 11 & 31) >> 2, (d >> 5 & 63) << 2 | (d >> 5 & 63) >> 4, (d & 31) << 3 | (d & 31) >> 2)
                c = 0
                for n, sh in enumerate((16, 8, 0)):
                    xx = (col >> sh & 255) * al + dd[n] * (255 - al)
                    c |= ((xx + 128 + ((xx + 128) >> 8)) >> 8) << sh
                col = c
            out[f"r_we{k}"] = 1
            out[f"r_waddr{k}"] = y * 80 + (x >> 2)
            out[f"r_wdata{k}"] = (col >> 19 & 31) << 11 | (col >> 10 & 63) << 5 | (col >> 3 & 31)
    return out


def vectors(rng):
    """Directed vectors: random inputs almost never make `act` true with positions on the screen. Positions mostly in or just outside
    the screen (some with garbage in the high bits), scissor boxes of every kind, lanes on the same bank, any tmask."""
    out = []
    for _ in range(1500):
        lanes = []
        base = rng.randrange(0, 90) * 4
        for l in range(4):
            r = rng.random()
            x = base + l if r < 0.5 else rng.randrange(0, 340) if r < 0.9 else rng.getrandbits(16)
            y = rng.randrange(0, 250) if rng.random() < 0.9 else rng.getrandbits(16)
            lanes.append(y << 16 | x)
        if rng.random() < 0.3:
            x = rng.randrange(0, 80) * 4
            lanes = [(rng.randrange(0, 240) << 16 | x + 4 * rng.randrange(0, 4)) if rng.random() < 0.8 else lanes[l] for l in range(4)]
        box = [rng.randrange(0, 330), rng.randrange(0, 250), rng.randrange(0, 512), rng.randrange(0, 512)]
        if rng.random() < 0.5:
            box = [0, 0, 320, 240]
        alpha = rng.choice([0, 255, 128, 1, 254, rng.randrange(256)])
        b_ = sum((rng.getrandbits(24) | alpha << 24) << 32 * l for l in range(4)) if rng.random() < 0.7 else rng.getrandbits(128)
        out.append({"blend": 1 if rng.random() < 0.5 else 0,
                    **{f"vw_rdata{k}": rng.choice([0, 0xFFFF, rng.getrandbits(16)]) for k in range(4)},
                    "valid": 1 if rng.random() < 0.95 else 0, "advance": 1 if rng.random() < 0.8 else 0,
                    "gfx": 1 if rng.random() < 0.95 else 0, "gfx_op": 5 if rng.random() < 0.9 else rng.randrange(8),
                    "tmask": 15 if rng.random() < 0.5 else rng.randrange(16),
                    "a": sum(v << 32 * l for l, v in enumerate(lanes)), "b": b_,
                    "sc_x0": box[0], "sc_y0": box[1], "sc_x1": box[2], "sc_y1": box[3]})
    return out
