"""Golden model of the warp table (block `warp_table`). Clocked, synchronous reset.

For each of the 4 warps: a 32-bit pc, a 4-bit thread mask and an in-flight bit. A warp is active when its mask is not 0.
Outputs (follow the state and fwid at once): sel_pc and sel_tmask are warp fwid's pc and mask; active and inflight are one
bit per warp (bit w for warp w); busy = 1 when any warp is active or in flight.
At each rising edge, in this order of priority:
  rst: every pc, mask and in-flight bit becomes 0.
  start (otherwise): warp 0 gets pc = start_pc and mask 0001; warps 1..3 get pc 0 and mask 0; every in-flight bit 0.
  otherwise all of these, each on its own warp:
    commit: warp cwid gets pc = c_pc, mask = c_tmask, in-flight 0.
    fire: warp fwid's in-flight bit becomes 1.
    spawn: each warp w whose spawn_mask bit is 1 and which, before this edge, has mask 0 and in-flight 0, gets pc = spawn_pc
           and mask 0001 (its in-flight bit is left to commit and fire); a spawn's pc and mask win over a commit's on the same warp.
Before the first reset the state is unknown.
"""

M = 0xFFFFFFFF


class WarpTable:
    def __init__(self):
        self.pc = self.tm = self.inf = None

    def outputs(self, i):
        if self.pc is None:
            return {"sel_pc": None, "sel_tmask": None, "active": None, "inflight": None, "busy": None}
        w = i["fwid"] & 3
        active = sum(1 << k for k in range(4) if self.tm[k])
        inflight = sum(1 << k for k in range(4) if self.inf[k])
        return {"sel_pc": self.pc[w], "sel_tmask": self.tm[w], "active": active, "inflight": inflight,
                "busy": int(bool(active or inflight))}

    def edge(self, i):
        if i["rst"] & 1:
            self.pc, self.tm, self.inf = [0] * 4, [0] * 4, [0] * 4
            return
        if self.pc is None:
            return
        if i["start"] & 1:
            self.pc, self.tm, self.inf = [i["start_pc"] & M, 0, 0, 0], [1, 0, 0, 0], [0] * 4
            return
        pc, tm, inf = list(self.pc), list(self.tm), list(self.inf)
        spawned = [w for w in range(4) if i["spawn_mask"] >> w & 1 and self.tm[w] == 0 and self.inf[w] == 0]
        if i["commit"] & 1:
            c = i["cwid"] & 3
            pc[c], tm[c], inf[c] = i["c_pc"] & M, i["c_tmask"] & 15, 0
        if i["fire"] & 1:
            inf[i["fwid"] & 3] = 1
        for w in spawned:                       # a spawn wins over a commit or a fire on the same warp
            pc[w], tm[w] = i["spawn_pc"] & M, 1
        self.pc, self.tm, self.inf = pc, tm, inf


def golden_warp_table(trace):
    m, out = WarpTable(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out
