"""Golden model of the warp scheduler (block `warp_sched`). Clocked, synchronous reset.

A warp is ready when it is active, has no instruction in flight and is not waiting at a barrier:
ready = active & ~inflight & ~waiting. When enable is 1 and some warp is ready, fire = 1 and fwid is the first ready warp
in the order ptr+1, ptr+2, ptr+3, ptr+4 (mod 4), where ptr is the warp chosen last (round robin); otherwise fire = 0 and
fwid = 0. Both outputs follow the inputs in the same cycle. At each rising edge: rst or start sets ptr to 3 (so warp 0 is
first); otherwise when fire is 1, ptr becomes fwid. Before the first reset ptr is unknown.
"""


class WarpSched:
    def __init__(self):
        self.ptr = None

    def outputs(self, i):
        ready = i["active"] & ~i["inflight"] & ~i["waiting"] & 15
        if not (i["enable"] & 1) or not ready:
            return {"fire": 0, "fwid": 0}
        if self.ptr is None:
            return {"fire": 1, "fwid": None}
        for k in range(1, 5):
            w = (self.ptr + k) % 4
            if ready >> w & 1:
                return {"fire": 1, "fwid": w}

    def edge(self, i):
        if i["rst"] & 1 or i["start"] & 1:
            self.ptr = 3
        else:
            o = self.outputs(i)
            if o["fire"] and o["fwid"] is not None:
                self.ptr = o["fwid"]


def golden_warp_sched(trace):
    m, out = WarpSched(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out
