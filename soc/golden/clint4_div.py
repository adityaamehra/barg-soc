"""Golden model of the four-hart core-local interruptor with a /16 prescaler (block `clint4_div`): mtime counts once every 16 cycles. Clocked. Written by hand.

Registers: msip[0..3] (1 bit each), mtimecmp[0..3] (64 bits, all ones at reset), mtime (64 bits, 0 at reset, shared). kind (1 msip,
2/3 mtimecmp low/high, 4/5 mtime low/high, other: none) and hart (0..3) name the register an access picks (hart is ignored for mtime).
rdata is the register before this cycle's write (0 for none). mtip<h> = mtime >= mtimecmp[h] as held; msip<h> = msip[h] as held.
At each edge: reset sets the reset values; else a store (we) writes the register (msip from wdata bit 0), and mtime counts up by one
unless the store was to a half of mtime (that half takes wdata, the other half stays). Before the first reset: outputs None."""

M32, M64 = 0xFFFFFFFF, (1 << 64) - 1


class Clint4:
    def __init__(self):
        self.s = None

    def outputs(self, i):
        s = self.s
        if s is None:
            return {"rdata": None, "mtime": None, **{f"mtip{h}": None for h in range(4)}, **{f"msip{h}": None for h in range(4)}}
        k, h = i["kind"] & 7, i["hart"] & 3
        rdata = {1: s["msip"][h], 2: s["cmp"][h] & M32, 3: s["cmp"][h] >> 32, 4: s["time"] & M32, 5: s["time"] >> 32}.get(k, 0)
        return {"rdata": rdata, "mtime": s["time"], **{f"mtip{x}": int(s["time"] >= s["cmp"][x]) for x in range(4)},
                **{f"msip{x}": s["msip"][x] for x in range(4)}}

    def edge(self, i):
        if i["rst"] & 1:
            self.s = {"msip": [0] * 4, "cmp": [M64] * 4, "time": 0, "pre": 0}
            return
        s = self.s
        if s is None:
            return
        k, h, w, counted = i["kind"] & 7, i["hart"] & 3, i["wdata"] & M32, True
        if i["we"] & 1:
            if k == 1:
                s["msip"][h] = w & 1
            elif k == 2:
                s["cmp"][h] = (s["cmp"][h] & ~M32 & M64) | w
            elif k == 3:
                s["cmp"][h] = (s["cmp"][h] & M32) | (w << 32)
            elif k == 4:
                s["time"], counted = (s["time"] & ~M32 & M64) | w, False
            elif k == 5:
                s["time"], counted = (s["time"] & M32) | (w << 32), False
        if counted and s["pre"] == 15:
            s["time"] = (s["time"] + 1) & M64
        s["pre"] = (s["pre"] + 1) & 15


def golden_clint4_div(trace):
    m, out = Clint4(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out


def traces(rng):
    out = []
    for _ in range(40):
        t = [{"rst": 1, "kind": 0, "hart": 0, "wdata": 0, "we": 0}]
        for _ in range(400):
            r = rng.random()
            w = rng.getrandbits(32) if r < 0.7 else rng.choice([0, 1, M32, 0xFFFFFFFE, 5, 7, 20, 30])
            if rng.random() < 0.3:            # make mtime reach a small mtimecmp: write small values to both
                w = rng.randrange(0, 12)
            t.append({"rst": int(rng.random() < 0.005), "kind": rng.choice([0, 1, 2, 3, 4, 5, 6, 7]), "hart": rng.getrandbits(2),
                      "wdata": w, "we": int(rng.random() < 0.4)})
        out.append(t)
    return out
