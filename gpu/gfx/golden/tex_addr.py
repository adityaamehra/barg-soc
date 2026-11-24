"""Golden model of the texture unit's read addresses (block `tex_addr`). Combinational. Never shown to the generator.

Lane l (lane l of a 128-bit bus is bits 32l+31..32l): u = lane l of a, v = lane l of b, unsigned 8.8 texels (bits 15:0 count):
iu = u bits 15:8, iv = v bits 15:8. Wrap of a coordinate c (0..256): repeat (mode bit 1 for u, bit 2 for v, = 0) c mod 32, clamp
min(c, 31). x0 = wrap_u(iu), x1 = wrap_u(iu + 1), y0 = wrap_v(iv), y1 = wrap_v(iv + 1). Lane l has its own four texture banks,
bank k = py * 2 + px holding the texels (tx, ty) with ty mod 2 = py and tx mod 2 = px, at index (ty >> 1) * 16 + (tx >> 1).
For bank k: xk = x0 when x0 mod 2 = px, else x1; yk = y0 when y0 mod 2 = py, else y1; ta<l><k> = (yk >> 1) * 16 + (xk >> 1)
(8 bits). These are the same whatever the filter (bit 0) and whether or not a tex is executing.
"""

M = 0xFFFFFFFF


def corners(u, v, mode):
    iu, iv = u >> 8 & 255, v >> 8 & 255
    wu = (lambda c: min(c, 31)) if mode & 2 else (lambda c: c % 32)
    wv = (lambda c: min(c, 31)) if mode & 4 else (lambda c: c % 32)
    return wu(iu), wu(iu + 1), wv(iv), wv(iv + 1)


def golden_tex_addr(a, b, tex_mode):
    out = {}
    for l in range(4):
        x0, x1, y0, y1 = corners(a >> 32 * l & M, b >> 32 * l & M, tex_mode)
        for k in range(4):
            py, px = k >> 1, k & 1
            xk = x0 if x0 & 1 == px else x1
            yk = y0 if y0 & 1 == py else y1
            out[f"ta{l}{k}"] = (yk >> 1) * 16 + (xk >> 1)
    return out


def coord(rng):
    """An 8.8 coordinate: mostly 0..64 texels (both wraps matter), the edges 31.x / 32.0 / 255.996, and junk above bit 15."""
    r = rng.random()
    c = (rng.randrange(0, 64 * 256) if r < 0.6 else rng.choice([31 * 256, 31 * 256 + 255, 32 * 256, 0, 255, 0xFFFF, 63 * 256 + 128])
         if r < 0.85 else rng.getrandbits(16))
    return c | (rng.getrandbits(16) << 16 if rng.random() < 0.2 else 0)


def vectors(rng):
    return [{"a": sum(coord(rng) << 32 * l for l in range(4)), "b": sum(coord(rng) << 32 * l for l in range(4)),
             "tex_mode": rng.randrange(8)} for _ in range(2000)]
