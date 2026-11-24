"""Golden model of the depth unit's control (block `z_ctrl`). Clocked, synchronous reset. Never shown to the generator.

ztest reads the depth memory in a first cycle and compares and writes in a second, so it holds the pipeline one cycle. Register:
pending (1 bit). Output at once: g_busy = in_busy | (valid & gfx & (gfx_op == 6) & !pending) (in_busy: the other graphics units'
requests, passed on to the pipeline control). At a rising edge: rst or clear: pending = 0; otherwise pending = 0 when advance is 1,
else 1 when valid & gfx & (gfx_op == 6), else unchanged. Before the first reset g_busy is unknown (1 when in_busy is 1).
"""


class ZCtrl:
    def __init__(self):
        self.pending = None

    def outputs(self, i):
        if self.pending is None:
            return {"g_busy": 1 if i["in_busy"] & 1 else None}
        own = i["valid"] & 1 and i["gfx"] & 1 and i["gfx_op"] & 7 == 6 and not self.pending
        return {"g_busy": int(bool(i["in_busy"] & 1 or own))}

    def edge(self, i):
        if i["rst"] & 1 or i["clear"] & 1:
            self.pending = 0
        elif self.pending is not None:
            if i["advance"] & 1:
                self.pending = 0
            elif i["valid"] & 1 and i["gfx"] & 1 and i["gfx_op"] & 7 == 6:
                self.pending = 1


def golden_z_ctrl(trace):
    m, out = ZCtrl(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out


def traces(rng):
    out = []
    for _ in range(40):
        trace = [{"rst": 1, "clear": 0, "valid": 0, "advance": 0, "gfx": 0, "gfx_op": 0, "in_busy": 0}]
        while len(trace) < 160:
            r = rng.random()
            base = {"rst": 0, "clear": 0, "valid": 1, "advance": 1, "gfx": 1, "gfx_op": 6, "in_busy": 1 if rng.random() < 0.1 else 0}
            if r < 0.5:
                for _ in range(rng.choice([1, 1, 1, 2])):
                    trace.append(dict(base, advance=0, clear=1 if rng.random() < 0.03 else 0))
                trace.append(dict(base))
            elif r < 0.9:
                trace.append(dict(base, gfx_op=rng.randrange(8), valid=rng.randrange(2), gfx=rng.randrange(2), advance=rng.randrange(2)))
            else:
                trace.append(dict(base, rst=1 if rng.random() < 0.5 else 0, clear=1, advance=rng.randrange(2)))
        out.append(trace)
    return out
