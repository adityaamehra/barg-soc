"""Golden model of the depth unit (block `z_unit`). Combinational. Never shown to the generator.

ztest: per lane l (lane l of a 128-bit bus is bits 32l+31..32l) with tmask bit l set, position = lane l of a (x = bits 15:0, y = bits
31:16) and depth z = lane l of b, bits 15:0. A lane tests when x < 320 and y < 240; it is on depth bank k = x bits 1:0 at index
y * 80 + (x >> 2). Per bank, the highest-numbered testing lane is the bank's winner; the other lanes on that bank do not test.
- z_raddr<k> (15 bits): when valid & gfx & (gfx_op == 6), the winner's index on bank k; 0 when bank k has no winner or otherwise.
- The winner of bank k passes when z < z_rdata<k> (the stored depth, read in the cycle before at z_raddr<k>).
- Writes, when valid & advance & gfx & (gfx_op == 6): for a passing winner of bank k, zw_we<k> = 1, zw_waddr<k> = its index,
  zw_wdata<k> = its z; zw_we<k> = 0 otherwise. zw_waddr<k> and zw_wdata<k> do not matter when zw_we<k> is 0 (None here).
- z_y: when gfx & (gfx_op == 6), lane l is 0xFFFFFFFF when lane l is a passing winner, else 0; every lane 0 otherwise.
"""

M = 0xFFFFFFFF


def golden_z_unit(valid, advance, gfx, gfx_op, tmask, a, b, z_rdata0, z_rdata1, z_rdata2, z_rdata3):
    rd = [z_rdata0, z_rdata1, z_rdata2, z_rdata3]
    out = {**{f"z_raddr{k}": 0 for k in range(4)}, **{f"zw_we{k}": 0 for k in range(4)},
           **{f"zw_waddr{k}": None for k in range(4)}, **{f"zw_wdata{k}": None for k in range(4)}, "z_y": 0}
    op = gfx & 1 and gfx_op & 7 == 6
    if not op:
        return out
    winner = {}
    for l in range(4):
        if tmask >> l & 1:
            pos = a >> 32 * l & M
            x, y = pos & 0xFFFF, pos >> 16
            if x < 320 and y < 240:
                winner[x & 3] = (l, y * 80 + (x >> 2), b >> 32 * l & 0xFFFF)
    for k, (l, idx, z) in winner.items():
        if valid & 1:
            out[f"z_raddr{k}"] = idx
        if z < rd[k] & 0xFFFF:
            out["z_y"] |= M << 32 * l
            if valid & 1 and advance & 1:
                out[f"zw_we{k}"], out[f"zw_waddr{k}"], out[f"zw_wdata{k}"] = 1, idx, z
    return out


def vectors(rng):
    """Positions in and around the screen, lanes sharing banks, depths equal to / just below / above the stored ones, junk above
    bit 15 of the depth, every tmask, valid/advance off, other ops."""
    out = []
    for _ in range(2000):
        base = rng.randrange(0, 80) * 4
        lanes = []
        for l in range(4):
            r = rng.random()
            x = base + l if r < 0.5 else rng.randrange(0, 330) if r < 0.9 else rng.getrandbits(16)
            y = rng.randrange(0, 245) if rng.random() < 0.9 else rng.getrandbits(16)
            lanes.append(y << 16 | x)
        stored = [rng.choice([0, 0xFFFF, 5000, rng.getrandbits(16)]) for _ in range(4)]
        zs = []
        for l in range(4):
            k = lanes[l] & 3
            zs.append(max(0, min(0xFFFF, stored[k] + rng.choice([-1, 0, 1, -300, 300]))) if rng.random() < 0.6 else rng.getrandbits(16))
        out.append({"valid": 1 if rng.random() < 0.9 else 0, "advance": 1 if rng.random() < 0.7 else 0,
                    "gfx": 1 if rng.random() < 0.95 else 0, "gfx_op": 6 if rng.random() < 0.9 else rng.randrange(8),
                    "tmask": 15 if rng.random() < 0.5 else rng.randrange(16), "a": sum(v << 32 * l for l, v in enumerate(lanes)),
                    "b": sum((z | rng.getrandbits(16) << 16 * (rng.random() < 0.3)) << 32 * l for l, z in enumerate(zs)),
                    **{f"z_rdata{k}": stored[k] for k in range(4)}})
    return out
