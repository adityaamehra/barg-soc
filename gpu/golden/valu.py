"""Golden model of the 4-lane ALU (block `valu`). Combinational; lane i of a 128-bit bus is bits 32i+31..32i.

Lane i: x = pc when a_sel is 1, else a_i; z = imm when b_sel is 1, else b_i. y_i = alu_op applied to x and z
(ADD, SUB, SLL, SLT, SLTU, XOR, SRL, SRA, OR, AND, PASS_B = z; codes 11..15 give 0; shifts use z bits 4:0).
taken_i compares a_i with b_i (never the selected operands) by br_op: 0 equal, 1 not equal, 4 signed less, 5 signed
greater-or-equal, 6 unsigned less, 7 unsigned greater-or-equal, 2 and 3 never.
"""

M = 0xFFFFFFFF


def _s(x):
    return x - (1 << 32) if x >> 31 else x


def _lane(v, i):
    return v >> 32 * i & M


def golden_valu(a, b, imm, pc, a_sel, b_sel, alu_op, br_op):
    y, taken = 0, 0
    for i in range(4):
        ai, bi = _lane(a, i), _lane(b, i)
        x = pc & M if a_sel & 1 else ai
        z = imm & M if b_sel & 1 else bi
        sh = z & 31
        r = {0: x + z, 1: x - z, 2: x << sh, 3: int(_s(x) < _s(z)), 4: int(x < z), 5: x ^ z, 6: x >> sh,
             7: _s(x) >> sh, 8: x | z, 9: x & z, 10: z}.get(alu_op, 0) & M
        y |= r << 32 * i
        t = {0: ai == bi, 1: ai != bi, 4: _s(ai) < _s(bi), 5: _s(ai) >= _s(bi), 6: ai < bi, 7: ai >= bi}.get(br_op, False)
        taken |= int(t) << i
    return {"y": y, "taken": taken}


EDGE = (0, 1, 2, 3, 4, 5, 31, 32, 0x7FFFFFFF, 0x80000000, 0x80000001, 0xFFFFFFFE, 0xFFFFFFFF, 0x12345678, 0xDEADBEEF)


def vectors(rng):
    """Directed vectors: small and edge values (loop counters, the sign boundary, all ones), which random 32-bit values almost
    never produce, in every operation."""
    out = []
    for _ in range(1500):
        out.append({"a": sum(rng.choice(EDGE) << 32 * i for i in range(4)), "b": sum(rng.choice(EDGE) << 32 * i for i in range(4)),
                    "imm": rng.choice(EDGE), "pc": rng.choice(EDGE) & ~3, "a_sel": rng.randrange(2), "b_sel": rng.randrange(2),
                    "alu_op": rng.randrange(16), "br_op": rng.randrange(8)})
    return out
