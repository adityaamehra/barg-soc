"""Golden model of the divergence (IPDOM) stacks (block `ipdom`). Clocked, synchronous reset.

One stack of up to 8 entries per warp; an entry is (mask 4 bits, pc 32 bits, fall 1 bit). Outputs for warp wid (at once):
depth (0..8), and the top entry (the one pushed last) as top_mask, top_pc, top_fall, or all 0 when depth is 0.
At each rising edge: rst or clear_all empties every stack. Otherwise, when en is 1, on warp wid's stack, the first that
applies: clear empties it; pop removes the top entry (nothing when empty); push 1 adds e0; push 2 adds e0 and then e1
(e1 on top). A push that would take the stack past 8 entries changes nothing. Before the first reset the stacks are unknown.
"""


class Ipdom:
    def __init__(self):
        self.stacks = None

    def outputs(self, i):
        if self.stacks is None:
            return {"depth": None, "top_mask": None, "top_pc": None, "top_fall": None}
        s = self.stacks[i["wid"] & 3]
        top = s[-1] if s else (0, 0, 0)
        return {"depth": len(s), "top_mask": top[0], "top_pc": top[1], "top_fall": top[2]}

    def edge(self, i):
        if i["rst"] & 1 or i["clear_all"] & 1:
            self.stacks = [[] for _ in range(4)]
            return
        if self.stacks is None or not i["en"] & 1:
            return
        s = self.stacks[i["wid"] & 3]
        e0 = (i["e0_mask"] & 15, i["e0_pc"] & 0xFFFFFFFF, i["e0_fall"] & 1)
        e1 = (i["e1_mask"] & 15, i["e1_pc"] & 0xFFFFFFFF, i["e1_fall"] & 1)
        if i["clear"] & 1:
            s.clear()
        elif i["pop"] & 1:
            if s:
                s.pop()
        elif i["push"] == 1 and len(s) + 1 <= 8:
            s.append(e0)
        elif i["push"] == 2 and len(s) + 2 <= 8:
            s.extend([e0, e1])


def golden_ipdom(trace):
    m, out = Ipdom(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out
