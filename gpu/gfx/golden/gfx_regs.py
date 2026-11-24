"""Golden model of the graphics state registers (block `gfx_regs`). Clocked, synchronous reset. Never shown to the generator.

Four 9-bit registers, the scissor box: x0 (gfx.cfg number 0), y0 (1), x1 (2), y1 (3). After reset, or when clear is 1, at the next
edge: x0 = 0, y0 = 0, x1 = 320, y1 = 240. Outputs (sc_x0, sc_y0, sc_x1, sc_y1) show the registers at once.
Otherwise at an edge where valid & advance & gfx & (gfx_op == 0, the gfx.cfg instruction) & (tmask != 0): the lowest-numbered lane l
with tmask bit l set gives the register number n = lane l of a (all 32 bits) and the value v = lane l of b; register n takes
v bits 8:0 when n is 0..3, and nothing changes for any other n. (Lane i of a 128-bit bus is bits 32i+31..32i.)
Before the first reset the outputs are unknown.
"""

M = 0xFFFFFFFF


class GfxRegs:
    def __init__(self):
        self.r = None

    def outputs(self, i):
        r = self.r
        return {"sc_x0": None if r is None else r[0], "sc_y0": None if r is None else r[1],
                "sc_x1": None if r is None else r[2], "sc_y1": None if r is None else r[3]}

    def edge(self, i):
        if i["rst"] & 1 or i["clear"] & 1:
            self.r = [0, 0, 320, 240]
        elif self.r is not None and i["valid"] & 1 and i["advance"] & 1 and i["gfx"] & 1 and i["gfx_op"] & 7 == 0 and i["tmask"] & 15:
            lane = next(k for k in range(4) if i["tmask"] >> k & 1)
            n, v = i["a"] >> 32 * lane & M, i["b"] >> 32 * lane & M
            if n < 4:
                self.r[n] = v & 0x1FF


def golden_gfx_regs(trace):
    m, out = GfxRegs(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out


def traces(rng):
    """Directed traces: a register changes only on a gfx.cfg (valid, advance, gfx, gfx_op 0) with some lane active, which random
    inputs rarely give. Mostly register numbers 0..4 (some large), mixed lane masks, now and then rst or clear."""
    out = []
    for _ in range(30):
        trace = []
        for cycle in range(100):
            number = lambda: rng.randrange(0, 5) if rng.random() < 0.9 else rng.getrandbits(32)
            trace.append({"rst": 1 if cycle == 0 or rng.random() < 0.01 else 0, "clear": 1 if rng.random() < 0.03 else 0,
                          "valid": 1 if rng.random() < 0.95 else 0, "advance": 1 if rng.random() < 0.85 else 0,
                          "gfx": 1 if rng.random() < 0.95 else 0, "gfx_op": 0 if rng.random() < 0.9 else rng.randrange(8),
                          "tmask": rng.randrange(16) if rng.random() < 0.7 else 15,
                          "a": sum(number() << 32 * l for l in range(4)), "b": rng.getrandbits(128)})
        out.append(trace)
    return out
