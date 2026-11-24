"""Golden model of the 4-lane multiplier (block `vmul`). Combinational.

Lane i: md_op 0 MUL (low 32 bits of a_i x b_i), 1 MULH (high 32 bits, both signed), 2 MULHSU (a signed, b unsigned),
3 MULHU (both unsigned).
"""

M = 0xFFFFFFFF


def _s(x):
    return x - (1 << 32) if x >> 31 else x


def golden_vmul(a, b, md_op):
    y = 0
    for i in range(4):
        x, z = a >> 32 * i & M, b >> 32 * i & M
        r = [(x * z), (_s(x) * _s(z)) >> 32, (_s(x) * z) >> 32, (x * z) >> 32][md_op & 3] & M
        y |= r << 32 * i
    return {"y": y}


EDGE = (0, 1, 2, 3, 4, 5, 31, 32, 0x7FFFFFFF, 0x80000000, 0x80000001, 0xFFFFFFFE, 0xFFFFFFFF, 0x12345678, 0xDEADBEEF)


def vectors(rng):
    """Directed vectors: small and edge values (loop counters, the sign boundary, all ones), which random 32-bit values almost
    never produce, in every operation."""
    out = []
    for _ in range(1500):
        out.append({"a": sum(rng.choice(EDGE) << 32 * i for i in range(4)), "b": sum(rng.choice(EDGE) << 32 * i for i in range(4)),
                    "md_op": rng.randrange(4)})
    return out
