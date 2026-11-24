"""Golden model of the raster-output control (block `rop_ctrl`). Clocked, synchronous reset. Never shown to the generator.

Registers: blend (1 bit, gfx.cfg number 4: 1 source-over, 0 replace) and pending (1 bit). With blending on, pix reads the destination
in a first cycle and writes in a second, so it holds the pipeline one cycle. Outputs at once: blend shows its register; g_busy =
tex_busy | (valid & gfx & (gfx_op == 5) & blend & !pending) (the texture unit's request and this unit's, for pipe_ctrl).
At a rising edge: rst or clear: blend = 0, pending = 0. Otherwise: pending = 0 when advance is 1, else pending = 1 when valid & gfx &
(gfx_op == 5) & blend, else unchanged; and when valid & advance & gfx & (gfx_op == 0) & (tmask != 0), with lane l the lowest lane
whose tmask bit is set, if lane l of a (all 32 bits) is 4, blend = bit 0 of lane l of b.
Before the first reset the outputs are unknown (g_busy too, unless tex_busy is 1).
"""

M = 0xFFFFFFFF


class RopCtrl:
    def __init__(self):
        self.pending = self.blend = None

    def outputs(self, i):
        if self.pending is None:
            return {"g_busy": 1 if i["tex_busy"] & 1 else None, "blend": None}
        own = i["valid"] & 1 and i["gfx"] & 1 and i["gfx_op"] & 7 == 5 and self.blend and not self.pending
        return {"g_busy": int(bool(i["tex_busy"] & 1 or own)), "blend": self.blend}

    def edge(self, i):
        if i["rst"] & 1 or i["clear"] & 1:
            self.pending, self.blend = 0, 0
            return
        if self.pending is None:
            return
        pix = i["valid"] & 1 and i["gfx"] & 1 and i["gfx_op"] & 7 == 5 and self.blend
        if i["valid"] & 1 and i["advance"] & 1 and i["gfx"] & 1 and i["gfx_op"] & 7 == 0 and i["tmask"] & 15:
            lane = next(k for k in range(4) if i["tmask"] >> k & 1)
            if i["a"] >> 32 * lane & M == 4:
                self.blend = i["b"] >> 32 * lane & 1
        if i["advance"] & 1:
            self.pending = 0
        elif pix:
            self.pending = 1


def golden_rop_ctrl(trace):
    m, out = RopCtrl(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out


def traces(rng):
    """As the pipeline drives it: gfx.cfg 4 turning blending on and off (also 4 with high bits, other numbers), pix held one cycle
    (or longer) when blending, tex_busy from the texture unit at any time, other ops, rst and clear (also while pending)."""
    out = []
    for _ in range(40):
        trace = [{"rst": 1, "clear": 0, "valid": 0, "advance": 0, "gfx": 0, "gfx_op": 0, "tmask": 0, "a": 0, "b": 0, "tex_busy": 0}]
        while len(trace) < 160:
            r = rng.random()
            base = {"rst": 0, "clear": 0, "valid": 1, "advance": 1, "gfx": 1, "gfx_op": 5, "tmask": 15,
                    "a": rng.getrandbits(128), "b": rng.getrandbits(128), "tex_busy": 1 if rng.random() < 0.1 else 0}
            if r < 0.4:
                for _ in range(rng.choice([1, 1, 1, 2])):
                    trace.append(dict(base, advance=0, clear=1 if rng.random() < 0.03 else 0))
                trace.append(dict(base))
            elif r < 0.6:
                tm = rng.choice([15, 1, 6, 8, 0])
                lane = next((k for k in range(4) if tm >> k & 1), 0)
                n = rng.choice([4, 4, 4, 0, 5, 32, 4 | 1 << 20, rng.getrandbits(32)])
                a = base["a"] & ~(M << 32 * lane) | (n & M) << 32 * lane
                trace.append(dict(base, gfx_op=0, tmask=tm, a=a, advance=rng.choice([1, 1, 1, 0])))
            elif r < 0.9:
                trace.append(dict(base, gfx_op=rng.randrange(8), valid=rng.randrange(2), gfx=rng.randrange(2),
                                  advance=rng.randrange(2)))
            else:
                trace.append(dict(base, rst=1 if rng.random() < 0.5 else 0, clear=1, advance=rng.randrange(2)))
        out.append(trace)
    return out
