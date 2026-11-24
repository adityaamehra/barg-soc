"""Golden model of the texture unit's filter (block `tex_filter`). Combinational. Never shown to the generator.

When gfx & (gfx_op == 4) (tex), lane l of tex_y is the texture sample at (u, v) = (lane l of a, lane l of b); otherwise every lane is
0. The texels come from lane l's four banks, read in the cycle before at the addresses tex_addr gives (the pipeline is held for
it): t<l><k> is bank k = py * 2 + px of lane l. With x0, x1, y0, y1 as in tex_addr (wrap per tex_mode bits 1 and 2) and fu = u bits
7:0, fv = v bits 7:0: the texel (xX, yY) is t<l><k> with k = (yY mod 2) * 2 + (xX mod 2). RGB565 to 8 bits: r8 = r5 << 3 | r5 >> 2,
g8 = g6 << 2 | g6 >> 4, b8 = b5 << 3 | b5 >> 2. Point (tex_mode bit 0 = 0): the texel (x0, y0). Bilinear: each channel is
(c00 (256 - fu)(256 - fv) + c10 fu (256 - fv) + c01 (256 - fu) fv + c11 fu fv + 32768) >> 16. The lane is 0xFF << 24 | r << 16 |
g << 8 | b.
"""

import random

M = 0xFFFFFFFF


def corners(u, v, mode):
    """x0, x1, y0, y1 of tex_addr (repeated here so that this file stands alone)."""
    iu, iv = u >> 8 & 255, v >> 8 & 255
    wu = (lambda c: min(c, 31)) if mode & 2 else (lambda c: c % 32)
    wv = (lambda c: min(c, 31)) if mode & 4 else (lambda c: c % 32)
    return wu(iu), wu(iu + 1), wv(iv), wv(iv + 1)


def coord(rng):
    r = rng.random()
    c = (rng.randrange(0, 64 * 256) if r < 0.6 else rng.choice([31 * 256, 31 * 256 + 255, 32 * 256, 0, 255, 0xFFFF, 63 * 256 + 128])
         if r < 0.85 else rng.getrandbits(16))
    return c | (rng.getrandbits(16) << 16 if rng.random() < 0.2 else 0)


def rgb(p):
    r5, g6, b5 = p >> 11 & 31, p >> 5 & 63, p & 31
    return r5 << 3 | r5 >> 2, g6 << 2 | g6 >> 4, b5 << 3 | b5 >> 2


def golden_tex_filter(gfx, gfx_op, a, b, tex_mode, t00, t01, t02, t03, t10, t11, t12, t13, t20, t21, t22, t23, t30, t31, t32, t33):
    t = {f"t{l}{k}": v for (l, k), v in zip([(l, k) for l in range(4) for k in range(4)], [t00, t01, t02, t03, t10, t11, t12, t13, t20, t21, t22, t23, t30, t31, t32, t33])}
    y = 0
    if not (gfx & 1 and gfx_op & 7 == 4):
        return {"tex_y": 0}
    for l in range(4):
        u, v = a >> 32 * l & M, b >> 32 * l & M
        x0, x1, y0, y1 = corners(u, v, tex_mode)
        fu, fv = u & 255, v & 255
        tx = lambda x, yy: rgb(t[f"t{l}{(yy & 1) * 2 + (x & 1)}"] & 0xFFFF)     # noqa: E731
        if not tex_mode & 1:
            c = tx(x0, y0)
        else:
            q = [tx(x0, y0), tx(x1, y0), tx(x0, y1), tx(x1, y1)]
            w = [(256 - fu) * (256 - fv), fu * (256 - fv), (256 - fu) * fv, fu * fv]
            c = tuple((sum(w[k] * q[k][ch] for k in range(4)) + 32768) >> 16 for ch in range(3))
        y |= (0xFF000000 | c[0] << 16 | c[1] << 8 | c[2]) << 32 * l
    return {"tex_y": y}


def vectors(rng):
    """Every mode, coordinates at the edges (31.x, 32.0, clamp), fractions 0 and 255, texels with extreme channels; a few other
    ops and gfx = 0."""
    out = []
    for _ in range(2500):
        fr = lambda: rng.choice([0, 255, 128, rng.randrange(256)])                 # noqa: E731
        cu = lambda: (coord(rng) & ~255) | fr()                                     # noqa: E731
        texel = lambda: rng.choice([0, 0xFFFF, 0xF800, 0x07E0, 0x001F, rng.getrandbits(16)])  # noqa: E731
        out.append({"gfx": 1 if rng.random() < 0.95 else 0, "gfx_op": 4 if rng.random() < 0.9 else rng.randrange(8),
                    "a": sum(cu() << 32 * l for l in range(4)), "b": sum(cu() << 32 * l for l in range(4)),
                    "tex_mode": rng.randrange(8), **{f"t{l}{k}": texel() for l in range(4) for k in range(4)}})
    return out


if __name__ == "__main__":
    # the filter and the address together against the frame model's sampler (gfx/scenes.py), on a random texture
    import sys
    sys.path.insert(0, "..")
    import scenes
    import tex_addr
    rng = random.Random(3)
    tex = [rng.getrandbits(16) for _ in range(32 * 32)]
    banks = [[0] * 256 for _ in range(4)]
    for t, p in enumerate(tex):
        ty, txx = divmod(t, 32)
        banks[(ty & 1) * 2 + (txx & 1)][(ty >> 1) * 16 + (txx >> 1)] = p
    for v in vectors(random.Random(4)):
        v.update(gfx=1, gfx_op=4)
        addr = tex_addr.golden_tex_addr(v["a"], v["b"], v["tex_mode"])
        rd = {f"t{l}{k}": banks[k][addr[f"ta{l}{k}"]] for l in range(4) for k in range(4)}
        got = golden_tex_filter(1, 4, v["a"], v["b"], v["tex_mode"], **rd)["tex_y"]
        for l in range(4):
            want = scenes.tex_sample(tex, v["tex_mode"], v["a"] >> 32 * l & 0xFFFF, v["b"] >> 32 * l & 0xFFFF)
            assert got >> 32 * l & M == want, (l, hex(got >> 32 * l & M), hex(want))
    print("tex_addr + tex_filter goldens agree with the frame model's sampler on 2500 x 4 samples")
