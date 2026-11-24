"""Golden model of the raster unit's evaluator (block `raster_eval`). Combinational. Never shown to the generator.

Edge function i (0..2) at pixel (x, y): E_i = ea<i> * x + eb<i> * y + ec<i>, all 32-bit, kept to 32 bits (wrapping); x and y are
unsigned. Lane l of a 128-bit bus is bits 32l+31..32l. The output y (128 bits):
- gfx & (gfx_op == 1), rast: when s_done is 1, every lane is 0xFFFFFFFF. Otherwise lane l is the pixel x = s_x + l (16 bits),
  row s_y: covered when for every i, E_i + bias bit i, taken as a signed 32-bit value (wrapping), is greater than 0; the lane is
  (s_y << 16) | x when covered, (0xFFFF << 16) | x when not.
- gfx & (gfx_op == 3), rast.edge: lane l takes position p = lane l of a (x = bits 15:0, y = bits 31:16) and edge number
  n = lane l of b, bits 1:0; the lane is E_n(x, y), or 0 when n is 3.
- otherwise every lane is 0.
"""

import random

M = 0xFFFFFFFF


def _e(c, i, x, y):
    return (c[3 * i] * x + c[3 * i + 1] * y + c[3 * i + 2]) & M


def golden_raster_eval(gfx, gfx_op, a, b, s_x, s_y, s_done, ea0, eb0, ec0, ea1, eb1, ec1, ea2, eb2, ec2, bias):
    c = [ea0, eb0, ec0, ea1, eb1, ec1, ea2, eb2, ec2]
    y = 0
    if gfx & 1 and gfx_op & 7 == 1:
        for l in range(4):
            if s_done & 1:
                v = M
            else:
                x, row = (s_x + l) & 0xFFFF, s_y & 0xFFFF
                cov = True
                for i in range(3):
                    t = (_e(c, i, x, row) + (bias >> i & 1)) & M
                    cov &= 0 < t < 1 << 31
                v = (row if cov else 0xFFFF) << 16 | x
            y |= v << 32 * l
    elif gfx & 1 and gfx_op & 7 == 3:
        for l in range(4):
            p, n = a >> 32 * l & M, b >> 32 * l & 3
            v = 0 if n == 3 else _e(c, n, p & 0xFFFF, p >> 16)
            y |= v << 32 * l
    return {"y": y}


def triangle(rng):
    """Coefficients of a triangle by the rule of the golden model (pixel units), some with vertices on pixel centres so that
    edges pass exactly through sample points; returns (coefficients, bias, box)."""
    def v():
        if rng.random() < 0.5:
            return 16 * rng.randrange(-8, 330) + 8, 16 * rng.randrange(-8, 250) + 8
        return rng.randrange(-200, 5300), rng.randrange(-200, 4000)
    while True:
        (x0, y0), (x1, y1), (x2, y2) = v(), v(), v()
        if rng.random() < 0.3:                                   # small triangles: every lane near an edge
            x1, y1, x2, y2 = x0 + rng.randrange(-80, 80), y0 + rng.randrange(-80, 80), x0 + rng.randrange(-80, 80), y0 + rng.randrange(-80, 80)
        a2 = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)
        if a2 != 0 or rng.random() < 0.05:
            break
    if a2 < 0:
        x1, y1, x2, y2 = x2, y2, x1, y1
    c, bias = [], 0
    for i, (ax, ay, bx, by) in enumerate(((x1, y1, x2, y2), (x2, y2, x0, y0), (x0, y0, x1, y1))):
        ex, ey = bx - ax, by - ay
        c += [(-16 * ey) & M, (16 * ex) & M, (ex * (8 - ay) - ey * (8 - ax)) & M]
        bias |= int(-ey > 0 or (ey == 0 and ex < 0)) << i
    box = (max(0, min(x0, x1, x2) >> 4), max(0, min(y0, y1, y2) >> 4), min(319, max(x0, x1, x2) >> 4), min(239, max(y0, y1, y2) >> 4))
    return c, bias, box


def vectors(rng):
    """Directed vectors from real triangles: rast at groups inside and around the box (s_x a multiple of 4), the done state, rast.edge
    at covered and uncovered positions (y = 0xFFFF) with all four edge numbers (3 gives 0) and junk in the high bits of b; a few
    other ops and gfx = 0 (output 0), and a few vectors with random coefficients and bias."""
    out = []
    for n in range(2500):
        c, bias, (xa, ya, xb, yb) = triangle(rng)
        if rng.random() < 0.1:
            c, bias = [rng.getrandbits(32) for _ in range(9)], rng.randrange(8)
        sx = (rng.randrange(max(0, xa - 8), min(511, max(xa, xb) + 8) + 1)) & ~3
        sy = rng.randrange(max(0, ya - 4), min(1023, max(ya, yb) + 4) + 1)
        lanes = []
        for l in range(4):
            px, py = (sx + l, sy) if rng.random() < 0.6 else (rng.randrange(0, 330), rng.randrange(0, 250))
            if rng.random() < 0.15:
                py = 0xFFFF
            lanes.append(py << 16 | px)
        r = rng.random()
        op = 1 if r < 0.45 else 3 if r < 0.9 else rng.randrange(8)
        out.append({"gfx": 1 if rng.random() < 0.95 else 0, "gfx_op": op,
                    "a": sum(v << 32 * l for l, v in enumerate(lanes)),
                    "b": sum((rng.randrange(4) | rng.getrandbits(30) << 2 * (rng.random() < 0.3)) << 32 * l for l in range(4)),
                    "s_x": sx, "s_y": sy, "s_done": 1 if rng.random() < 0.1 else 0,
                    **{f"e{k}{i}": c[3 * i + j] for i in range(3) for j, k in enumerate("abc")}, "bias": bias})
    return out


if __name__ == "__main__":
    vs = vectors(random.Random(1))
    outs = [golden_raster_eval(**v)["y"] for v in vs]
    cov = sum(1 for v, y in zip(vs, outs) if v["gfx"] and v["gfx_op"] == 1 and not v["s_done"]
              for l in range(4) if (y >> 32 * l + 16 & 0xFFFF) != 0xFFFF)
    print(len(vs), "vectors,", cov, "covered lanes in rast vectors")
