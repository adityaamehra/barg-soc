"""Golden model of the barriers (block `barrier_unit`). Clocked, synchronous reset.

Four barriers, each with a 4-bit arrived mask (bit w: warp w has arrived), and a 4-bit waiting output (bit w: warp w waits;
it shows the state at once). At each rising edge: rst or clear_all: every arrived mask and waiting bit 0. Otherwise when en
is 1: m = arrived[bar_id] | (1 << wid). When the number of 1 bits in m is at least bar_count, the barrier releases:
arrived[bar_id] = 0 and every warp in m stops waiting (waiting &= ~m). Otherwise arrived[bar_id] = m and warp wid waits.
Before the first reset the state is unknown.
"""


class Barrier:
    def __init__(self):
        self.arrived, self.waiting = None, None

    def outputs(self, i):
        return {"waiting": self.waiting}

    def edge(self, i):
        if i["rst"] & 1 or i["clear_all"] & 1:
            self.arrived, self.waiting = [0] * 4, 0
            return
        if self.arrived is None or not i["en"] & 1:
            return
        b = i["bar_id"] & 3
        m = self.arrived[b] | 1 << (i["wid"] & 3)
        if bin(m).count("1") >= i["bar_count"]:
            self.arrived[b] = 0
            self.waiting &= ~m & 15
        else:
            self.arrived[b] = m
            self.waiting |= 1 << (i["wid"] & 3)


def golden_barrier_unit(trace):
    m, out = Barrier(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out
