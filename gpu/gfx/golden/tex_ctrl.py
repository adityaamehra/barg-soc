"""Golden model of the texture unit's control (block `tex_ctrl`). Clocked, synchronous reset. Never shown to the generator.

tex reads synchronous memories, so it holds the pipeline for exactly one cycle. Registers: pending (1 bit) and tex_mode (3 bits,
gfx.cfg number 32: bit 0 bilinear, bit 1 clamp u, bit 2 clamp v). Outputs at once: g_busy = valid & gfx & (gfx_op == 4) & !pending;
tex_mode shows its register.
At a rising edge: rst or clear: pending = 0, tex_mode = 0. Otherwise: pending = 0 when advance is 1, else pending = 1 when
valid & gfx & (gfx_op == 4), else unchanged; and when valid & advance & gfx & (gfx_op == 0) & (tmask != 0), with lane l the lowest
lane whose tmask bit is set, if lane l of a (all 32 bits) is 32, tex_mode = lane l of b, bits 2:0.
Before the first reset the outputs are unknown (g_busy too, as it reads pending).
"""

M = 0xFFFFFFFF


class TexCtrl:
    def __init__(self):
        self.pending = self.mode = None

    def outputs(self, i):
        if self.pending is None:
            return {"g_busy": None, "tex_mode": None}
        return {"g_busy": int(bool(i["valid"] & 1 and i["gfx"] & 1 and i["gfx_op"] & 7 == 4 and not self.pending)),
                "tex_mode": self.mode}

    def edge(self, i):
        if i["rst"] & 1 or i["clear"] & 1:
            self.pending, self.mode = 0, 0
            return
        if self.pending is None:
            return
        tex = i["valid"] & 1 and i["gfx"] & 1 and i["gfx_op"] & 7 == 4
        cfg = i["valid"] & 1 and i["advance"] & 1 and i["gfx"] & 1 and i["gfx_op"] & 7 == 0 and i["tmask"] & 15
        if cfg:
            lane = next(k for k in range(4) if i["tmask"] >> k & 1)
            if i["a"] >> 32 * lane & M == 32:
                self.mode = i["b"] >> 32 * lane & 7
        if i["advance"] & 1:
            self.pending = 0
        elif tex:
            self.pending = 1


def golden_tex_ctrl(trace):
    m, out = TexCtrl(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out


def traces(rng):
    """As the pipeline drives it: a tex instruction sits in X with advance 0 for one cycle (the stall) and then 1; sometimes a
    longer stall, a tex that is not valid, other ops; gfx.cfg of 32 and of other numbers (also 32 with high bits set), lane masks,
    rst and clear in between (also during a pending tex)."""
    out = []
    for _ in range(40):
        trace = [{"rst": 1, "clear": 0, "valid": 0, "advance": 0, "gfx": 0, "gfx_op": 0, "tmask": 0, "a": 0, "b": 0}]
        while len(trace) < 160:
            r = rng.random()
            base = {"rst": 0, "clear": 0, "valid": 1, "advance": 1, "gfx": 1, "gfx_op": 4, "tmask": 15,
                    "a": rng.getrandbits(128), "b": rng.getrandbits(128)}
            if r < 0.45:                                       # a tex: stalled, then advancing
                for _ in range(rng.choice([1, 1, 1, 2, 3])):
                    trace.append(dict(base, advance=0, clear=1 if rng.random() < 0.03 else 0))
                trace.append(dict(base))
            elif r < 0.65:
                tm = rng.choice([15, 1, 6, 8, 0])
                lane = next((k for k in range(4) if tm >> k & 1), 0)
                n = rng.choice([32, 32, 0, 25, 33, 32 | 1 << 32 * 0 + 8, rng.getrandbits(32)])
                a = base["a"] & ~(M << 32 * lane) | (n & M) << 32 * lane
                trace.append(dict(base, gfx_op=0, tmask=tm, a=a, advance=rng.choice([1, 1, 1, 0])))
            elif r < 0.9:
                trace.append(dict(base, gfx_op=rng.randrange(8), valid=rng.randrange(2), gfx=rng.randrange(2),
                                  advance=rng.randrange(2)))
            else:
                trace.append(dict(base, rst=1 if rng.random() < 0.5 else 0, clear=1, advance=rng.randrange(2)))
        out.append(trace)
    return out
