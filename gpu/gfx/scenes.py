"""G2a scenes and their frame model, written from the triangle rule (not from the kernel gfx/sw/tri.c).

    scene(name) -> (clear_argb, [Tri, ...])      frame(clear, tris) -> 320 x 240 RGB565 list      covered(tris) -> pixels drawn

A Tri is (x0, y0, x1, y1, x2, y2, c0, c1, c2, mode): coordinates in 1/16 pixel, colours ARGB8888, mode 0 flat, 1 Gouraud,
2 textured (G2c: c_i = v_i << 16 | u_i in 8.8 texels; mode bits 6:4 are the texture mode of gfx.cfg 32); mode bit 7 draws the
triangle with source-over blending (G2c-2, gfx.cfg 4); mode bit 8 depth-tests it (G2d) with vertex depths z0, z1, z2 (0..16383),
the optional 11th to 13th values of the tuple (scene() always returns 13). depth_clear(name) is the value the host writes into the
depth memory before the kernel, or None.
texture(name) is the 32 x 32 RGB565 texture a scene needs, or None.
"""

from __future__ import annotations

import random

W, H = 320, 240
MAXT = 32


def rgb565(argb: int) -> int:
    return (argb >> 19 & 31) << 11 | (argb >> 10 & 63) << 5 | (argb >> 3 & 31)


def setup(t):
    """The triangle with area2 > 0 (vertices 1 and 2 swapped when it was negative), its edges and biases; None when area2 = 0."""
    x0, y0, x1, y1, x2, y2, c0, c1, c2, mode = t[:10]
    z0, z1, z2 = (tuple(t[10:13]) + (0, 0, 0))[:3]
    a2 = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)
    if a2 == 0:
        return None
    if a2 < 0:
        x1, y1, x2, y2, c1, c2, z1, z2, a2 = x2, y2, x1, y1, c2, c1, z2, z1, -a2
    v = [(x0, y0), (x1, y1), (x2, y2)]
    edges = []
    for i in range(3):
        (ax, ay), (bx, by) = v[(i + 1) % 3], v[(i + 2) % 3]          # edge 0: v1 -> v2, 1: v2 -> v0, 2: v0 -> v1
        A, B = ay - by, bx - ax
        edges.append((ax, ay, bx, by, 1 if A > 0 or (A == 0 and B < 0) else 0))
    return a2, edges, (c0, c1, c2), mode, (z0, z1, z2)


def pixels(t, tex=None, want_z=False):
    """(x, y, argb) of every covered pixel of triangle t, on the screen; (x, y, argb, z) with want_z."""
    s_ = setup(t)
    if s_ is None:
        return
    a2, edges, cols, mode, zs = s_
    s = 0
    while (a2 >> s) >= 1 << 16:
        s += 1
    Wt = a2 >> s
    R = 0xFFFFFFFF // Wt
    ys = [t[1], t[3], t[5]]
    for y in range(max(0, min(ys) // 16 - 1), min(H, max(ys) // 16 + 2)):
        py = 16 * y + 8
        for x in range(W):
            px = 16 * x + 8
            E = [(bx - ax) * (py - ay) - (by - ay) * (px - ax) for ax, ay, bx, by, _ in edges]
            if not all(E[i] + edges[i][4] > 0 for i in range(3)):
                continue
            w = [e >> s for e in E]
            z = (sum(w[i] * zs[i] for i in range(3)) * R) >> 32
            if mode & 15 == 0:
                yield (x, y, cols[0], z) if want_z else (x, y, cols[0])
                continue
            if mode & 15 == 2:
                u = (sum(w[i] * (cols[i] & 0xFFFF) for i in range(3)) * R) >> 32
                v = (sum(w[i] * (cols[i] >> 16) for i in range(3)) * R) >> 32
                c = tex_sample(tex or [0] * (TW * TW), mode >> 4 & 7, u, v)
                yield (x, y, c, z) if want_z else (x, y, c)
                continue
            out = 0xFF000000
            for sh in (16, 8, 0):
                n = sum(w[i] * (cols[i] >> sh & 255) for i in range(3))
                v = (n * R) >> 32
                assert v <= 255, "the rule says a covered pixel's channel is at most 255"
                out |= v << sh
            yield (x, y, out, z) if want_z else (x, y, out)


TW = 32


def tex_sample(tex, mode, u, v):
    """The tex rule (G2c-1), written from the text."""
    def wrap(c, clamp):
        return min(c, TW - 1) if clamp else c % TW

    def rgb(p):
        r5, g6, b5 = p >> 11 & 31, p >> 5 & 63, p & 31
        return (r5 << 3 | r5 >> 2, g6 << 2 | g6 >> 4, b5 << 3 | b5 >> 2)
    iu, iv, fu, fv = u >> 8 & 255, v >> 8 & 255, u & 255, v & 255
    cu, cv = mode >> 1 & 1, mode >> 2 & 1
    if mode & 1 == 0:
        c = rgb(tex[wrap(iv, cv) * TW + wrap(iu, cu)])
    else:
        x0, x1, y0, y1 = wrap(iu, cu), wrap(iu + 1, cu), wrap(iv, cv), wrap(iv + 1, cv)
        q = [rgb(tex[y * TW + x]) for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
        w = [(256 - fu) * (256 - fv), fu * (256 - fv), (256 - fu) * fv, fu * fv]
        c = tuple((sum(w[k] * q[k][ch] for k in range(4)) + 32768) >> 16 for ch in range(3))
    return 0xFF000000 | c[0] << 16 | c[1] << 8 | c[2]


def texture(name: str):
    if not name.startswith("tex"):
        return None
    t = []
    for y in range(TW):
        for x in range(TW):
            check = ((x >> 2) ^ (y >> 2)) & 1
            r, g, b = (x * 31 // 31, 63 - 2 * y, 31 * check) if (x + y) % 7 else (31, 63, 0)
            t.append(r << 11 | g << 5 | b)
    return t


def frame(clear: int, tris, tex=None, zclear=None) -> list[int]:
    f = [rgb565(clear)] * (W * H)
    depth = [0 if zclear is None else zclear] * (W * H)
    for t in tris:
        for x, y, c, z in pixels(t, tex, want_z=True):
            p = y * W + x
            if t[9] >> 8 & 1:                                   # depth test: drawn when nearer, and the depth kept
                if not z < depth[p]:
                    continue
                depth[p] = z
            if t[9] >> 7 & 1:
                c = over(c, f[p])
            f[p] = rgb565(c)
    return f


def depth_clear(name: str):
    return 0xFFFF if name.startswith(("depth", "cube")) else None


def _cube(k: int, angle: float):
    """A cube rotated about two axes, projected: 12 flat triangles with depth (0..16383), one colour per face."""
    import math
    v = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    ca, sa, cb, sb = math.cos(angle), math.sin(angle), math.cos(0.6), math.sin(0.6)
    out = []
    for x, y, z in v:
        x, z = x * ca + z * sa, -x * sa + z * ca
        y, z = y * cb - z * sb, y * sb + z * cb
        s_ = 70 / (4 + z) * 4 / k
        out.append((int(16 * (160 / k + x * s_ * 1.0)), int(16 * (120 / k + y * s_)), int((z + 2) / 4 * 16000)))
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    cols = [0xFFE04040, 0xFF40E040, 0xFF4040E0, 0xFFE0E040, 0xFF40E0E0, 0xFFE040E0]
    tris = []
    for f, c in zip(faces, cols):
        a, b, cc, d = (out[i] for i in f)
        for p, q, r in ((a, b, cc), (a, cc, d)):
            tris.append((p[0], p[1], q[0], q[1], r[0], r[1], c, 0, 0, 1 << 8, p[2], q[2], r[2]))
    return tris


def over(src: int, dst565: int) -> int:
    """Source-over of ARGB8888 src on an RGB565 pixel, by the rule of G2c-2: x = s a + d (255 - a), rounded x / 255."""
    a = src >> 24 & 255
    d = ((dst565 >> 11 & 31) << 3 | (dst565 >> 11 & 31) >> 2, (dst565 >> 5 & 63) << 2 | (dst565 >> 5 & 63) >> 4,
         (dst565 & 31) << 3 | (dst565 & 31) >> 2)
    out = 0
    for k, sh in enumerate((16, 8, 0)):
        x = (src >> sh & 255) * a + d[k] * (255 - a)
        out |= ((x + 128 + ((x + 128) >> 8)) >> 8) << sh
    return out


def covered(tris) -> int:
    return sum(1 for t in tris for _ in pixels(t))


def bbox_pixels(tris) -> int:
    n = 0
    for t in tris:
        if setup(t) is None:
            continue
        xs, ys = [t[0], t[2], t[4]], [t[1], t[3], t[5]]
        xa, xb = max(0, min(xs) >> 4) & ~3, min(W - 1, max(xs) >> 4)
        ya, yb = max(0, min(ys) >> 4), min(H - 1, max(ys) >> 4)
        n += max(0, xb - xa + 1) * max(0, yb - ya + 1)
    return n


def _mesh(rnd, cx, cy, r, n, mode):
    """A fan of n triangles around (cx, cy) in pixels: every inner edge is shared by two triangles in opposite directions."""
    import math
    pts = [(int(16 * (cx + r * math.cos(2 * math.pi * k / n))), int(16 * (cy + r * math.sin(2 * math.pi * k / n)))) for k in range(n)]
    out = []
    for k in range(n):
        (ax, ay), (bx, by) = pts[k], pts[(k + 1) % n]
        out.append((16 * cx, 16 * cy, ax, ay, bx, by, *(0xFF000000 | rnd.getrandbits(24) for _ in range(3)), mode))
    return out


def scene(name: str, seed: int = 7):
    clear, tris = _scene(name, seed)
    return clear, [tuple(t) + (0,) * (13 - len(t)) for t in tris]


def _scene(name: str, seed: int = 7):
    rnd = random.Random(seed)
    if name == "clear":
        return 0xFF203040, []
    if name == "flat":
        tris = [(rnd.randrange(-400, 5520), rnd.randrange(-400, 4240), rnd.randrange(-400, 5520), rnd.randrange(-400, 4240),
                 rnd.randrange(-400, 5520), rnd.randrange(-400, 4240), 0xFF000000 | rnd.getrandbits(24), 0, 0, 0) for _ in range(6)]
        tris += _mesh(rnd, 80, 120, 50, 6, 0)
        tris += [(16 * 200, 16 * 40, 16 * 300, 16 * 40, 16 * 200, 16 * 140, 0xFFFF0000, 0, 0, 0),     # a square split along
                 (16 * 300, 16 * 40, 16 * 300, 16 * 140, 16 * 200, 16 * 140, 0xFF00FF00, 0, 0, 0),     # its diagonal
                 (100, 100, 900, 900, 1700, 1700, 0xFFFFFFFF, 0, 0, 0)]                               # zero area
        return 0xFF102030, tris
    if name == "gouraud":
        tris = [(16 * 10, 16 * 230, 16 * 160, 16 * 10, 16 * 310, 16 * 230, 0xFFFF0000, 0xFF00FF00, 0xFF0000FF, 1)]
        tris += _mesh(rnd, 240, 160, 40, 5, 1)
        tris += [(rnd.randrange(0, 5120), rnd.randrange(0, 3840), rnd.randrange(0, 5120), rnd.randrange(0, 3840),
                  rnd.randrange(0, 5120), rnd.randrange(0, 3840), *(0xFF000000 | rnd.getrandbits(24) for _ in range(3)), 1)
                 for _ in range(3)]
        return 0xFF000000, tris
    if name in ("tex", "tex_small"):
        k = 1 if name == "tex" else 4                         # tex_small: the same scene, a quarter of the size
        def T(p):                                             # pixel -> 1/16 pixel
            return 16 * p // k
        uv = lambda u, v: v << 16 | u                        # noqa: E731  (8.8 texels)
        tris = [  # a quad, bilinear, repeat both: the texture twice across, once down
                (T(20), T(20), T(180), T(20), T(20), T(140), uv(0, 0), uv(64 * 256, 0), uv(0, 32 * 256), 2 | 1 << 4),
                (T(180), T(20), T(180), T(140), T(20), T(140), uv(64 * 256, 0), uv(64 * 256, 32 * 256), uv(0, 32 * 256), 2 | 1 << 4),
                # point, clamp both: u and v run past 31, so the last row and column stretch
                (T(200), T(20), T(310), T(40), T(220), T(150), uv(0, 0), uv(48 * 256, 0), uv(0, 44 * 256), 2 | 6 << 4),
                # point, repeat u, clamp v; bilinear, clamp u, repeat v
                (T(30), T(160), T(150), T(170), T(60), T(235), uv(200, 10 * 256), uv(40 * 256 + 77, 3 * 256), uv(5 * 256, 40 * 256), 2 | 4 << 4),
                (T(170), T(160), T(310), T(180), T(200), T(235), uv(31 * 256 + 128, 0), uv(60 * 256, 31 * 256 + 200), uv(2 * 256, 50 * 256), 2 | 3 << 4)]
        return 0xFF202020, tris
    if name in ("blend", "blend_small"):
        k = 1 if name == "blend" else 4
        def T(p):
            return 16 * p // k
        B = 1 << 7
        tris = [(T(10), T(10), T(200), T(10), T(10), T(200), 0xFF2040C0, 0xFFC04020, 0xFF20C040, 1),          # Gouraud, opaque
                (T(60), T(40), T(300), T(60), T(120), T(230), 0x80FF0000, 0, 0, 0 | B),                       # half red
                (T(150), T(20), T(310), T(200), T(40), T(220), 0x4000FF00, 0, 0, 0 | B),                      # quarter green
                (T(5), T(150), T(100), T(235), T(5), T(235), 0x00FFFFFF, 0, 0, 0 | B),                        # alpha 0: nothing
                (T(200), T(150), T(315), T(235), T(200), T(235), 0xFF0000FF, 0, 0, 0 | B),                    # alpha 255: replace
                (T(100), T(100), T(220), T(110), T(130), T(200), 0xC0FFFFFF, 0, 0, 0)]                        # no blend: alpha ignored
        return 0xFF304050, tris
    if name.startswith("depth"):
        k = 4 if name.endswith("_small") else 1
        def T(p):
            return 16 * p // k
        D = 1 << 8
        a = (T(20), T(30), T(300), T(60), T(60), T(220), 0xFFE03030, 0, 0, D, 2000, 14000, 8000)       # leans back to the right
        b = (T(40), T(200), T(290), T(20), T(280), T(230), 0xFF3030E0, 0, 0, D, 12000, 3000, 9000)     # crosses it
        c = (T(100), T(100), T(200), T(120), T(150), T(200), 0xFF30E030, 0, 0, 1, 5000, 5000, 5000)    # Gouraud, no test
        tris = [a, b] if "_swap" not in name else [b, a]
        return 0xFF101010, tris + ([c] if "_swap" not in name else [])
    if name.startswith("cube"):
        return 0xFF000010, _cube(4 if name.endswith("_small") else 1, 0.5)
    if name == "small":                                        # few pixels, for the slow netlist of golden models
        tris = [(16 * 4 + 3, 16 * 2, 16 * 40, 16 * 9 + 5, 16 * 9, 16 * 30, 0xFFFF8000, 0xFF00FF80, 0xFF8000FF, 1),
                (16 * 40, 16 * 9 + 5, 16 * 9, 16 * 30, 16 * 44, 16 * 28, 0xFF30C0F0, 0, 0, 0),     # shares an edge with the first
                (16 * 50 + 8, 16 * 4 + 8, 16 * 60 + 8, 16 * 4 + 8, 16 * 50 + 8, 16 * 14 + 8, 0xFFFFFFFF, 0, 0, 0),  # edges on centres
                (16 * 320 - 40, 16 * 20, 16 * 330, 16 * 34, 16 * 310, 16 * 36, 0xFFFF0000, 0xFF00FF00, 0xFF0000FF, 1)]  # off the right
        return 0xFF102030, tris
    raise KeyError(name)


SCENES = ("clear", "flat", "gouraud")         # G2a / G2b; "tex" and "tex_small" need the tex instruction (G2c)


def self_check() -> None:
    """The rule against its own promises: a fan or a split square covers each pixel at most once (top-left rule)."""
    rnd = random.Random(1)
    for tris in (_mesh(rnd, 160, 120, 90, 7, 0), scene("flat")[1][-3:-1]):
        seen: dict[tuple[int, int], int] = {}
        for t in tris:
            for x, y, _ in pixels(t):
                seen[(x, y)] = seen.get((x, y), 0) + 1
        assert max(seen.values()) == 1, "a pixel on a shared edge was covered twice"


if __name__ == "__main__":
    self_check()
    for n in SCENES:
        c, tris = scene(n)
        print(f"{n:8} {len(tris):2} triangles, {covered(tris)} covered pixels, {bbox_pixels(tris)} bounding-box pixels")
