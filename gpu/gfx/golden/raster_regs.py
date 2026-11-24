"""Golden model of the raster unit's state (block `raster_regs`). Clocked, synchronous reset. Never shown to the generator.

State: the box x0, y0, x1, y1 (9 bits each), nine 32-bit edge coefficients (gfx.cfg numbers 16..24: ea0 eb0 ec0 ea1 eb1 ec1 ea2 eb2
ec2), the 3-bit bias (number 25), and for each warp w (0..3) a scan: sx_w, sy_w (10 bits each) and done_w (1 bit).
Outputs: ea0..ec2 and bias show their registers; s_x, s_y, s_done show the scan of warp `wid` (an input), at once.
At a rising edge:
- rst or clear: box, coefficients and bias 0; every scan sx = sy = 0, done = 1.
- else when valid & advance & gfx & (tmask != 0), with lane l = the lowest-numbered lane whose tmask bit is 1:
  - gfx_op 0 (gfx.cfg): number n = lane l of a (32 bits), value v = lane l of b. n = 8: x0 = v bits 8:0 with bits 1:0 made 0,
    y0 = v bits 24:16, and every warp w's scan restarts: sx_w = that x0, sy_w = y0 + ((w - y0) mod 4) (the first row at or
    below y0 with row mod 4 = w), done_w = 1 when sy_w > y1 or x0 > x1 (the y1, x1 held before this edge), else 0.
    n = 9: x1 = v bits 8:0, y1 = v bits 24:16. n = 16..24: that coefficient = v. n = 25: bias = v bits 2:0. Other n: nothing.
  - gfx_op 1 (rast), for warp w = wid when done_w is 0: when sx_w + 4 > x1, sx_w = x0, sy_w = sy_w + 4 and done_w = 1 when the
    new sy_w > y1; otherwise sx_w = sx_w + 4.
  - other gfx_op: nothing.
Before the first reset the outputs are unknown.
"""

M = 0xFFFFFFFF


class RasterRegs:
    def __init__(self):
        self.ok = False

    def reset(self):
        self.ok = True
        self.box = [0, 0, 0, 0]
        self.c = [0] * 9
        self.bias = 0
        self.scan = [[0, 0, 1] for _ in range(4)]

    def outputs(self, i):
        if not self.ok:
            return {**{f"e{k}{n}": None for n in range(3) for k in "abc"}, "bias": None, "s_x": None, "s_y": None, "s_done": None}
        sx, sy, d = self.scan[i["wid"] & 3]
        return {**{f"e{k}{n}": self.c[3 * n + j] for n in range(3) for j, k in enumerate("abc")}, "bias": self.bias,
                "s_x": sx, "s_y": sy, "s_done": d}

    def edge(self, i):
        if i["rst"] & 1 or i["clear"] & 1:
            self.reset()
            return
        if not self.ok or not (i["valid"] & 1 and i["advance"] & 1 and i["gfx"] & 1 and i["tmask"] & 15):
            return
        lane = next(k for k in range(4) if i["tmask"] >> k & 1)
        op = i["gfx_op"] & 7
        if op == 0:
            n, v = i["a"] >> 32 * lane & M, i["b"] >> 32 * lane & M
            if n == 8:
                x0, y0 = v & 0x1FC, v >> 16 & 0x1FF
                x1, y1 = self.box[2], self.box[3]
                self.box[0], self.box[1] = x0, y0
                for w in range(4):
                    sy = y0 + ((w - y0) & 3)
                    self.scan[w] = [x0, sy, int(sy > y1 or x0 > x1)]
            elif n == 9:
                self.box[2], self.box[3] = v & 0x1FF, v >> 16 & 0x1FF
            elif 16 <= n <= 24:
                self.c[n - 16] = v
            elif n == 25:
                self.bias = v & 7
        elif op == 1:
            w = i["wid"] & 3
            sx, sy, d = self.scan[w]
            if not d:
                if sx + 4 > self.box[2]:
                    sx, sy = self.box[0], sy + 4
                    d = int(sy > self.box[3])
                else:
                    sx += 4
                self.scan[w] = [sx & 0x3FF, sy & 0x3FF, d]


def golden_raster_regs(trace):
    m, out = RasterRegs(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out


def traces(rng):
    """Directed traces, as a kernel drives the unit: after reset, boxes (9 then 8) of every size (empty, one group, one row,
    off the end), coefficients and bias, then rast from random warps until their scans finish, with gfx.cfg of other numbers,
    other ops, valid/advance/gfx off, tmask 0 and sometimes rst or clear in between."""
    out = []
    for _ in range(40):
        trace = []

        def step(**kw):
            base = {"rst": 0, "clear": 0, "valid": 1, "advance": 1, "gfx": 1, "gfx_op": 1, "tmask": 15,
                    "wid": rng.randrange(4), "a": rng.getrandbits(128), "b": rng.getrandbits(128)}
            if rng.random() < 0.08:
                base.update(valid=rng.randrange(2), advance=rng.randrange(2), gfx=rng.randrange(2))
            if rng.random() < 0.05:
                base["tmask"] = rng.choice([0, 1, 2, 4, 8, rng.randrange(16)])
            base.update(kw)
            trace.append(base)

        def cfg(n, v):
            tm = rng.choice([15, 15, 2, 12, 6])
            lane = next(k for k in range(4) if tm >> k & 1)
            a, b = rng.getrandbits(128), rng.getrandbits(128)
            a = a & ~(M << 32 * lane) | n << 32 * lane
            b = b & ~(M << 32 * lane) | (v & M) << 32 * lane
            step(gfx_op=0, tmask=tm, a=a, b=b, valid=1, advance=1, gfx=1)

        step(rst=1)
        while len(trace) < 200:
            r = rng.random()
            if r < 0.4:
                x0, y0 = rng.randrange(0, 330), rng.randrange(0, 250)
                x1 = x0 + rng.choice([0, 1, 3, 4, 9, rng.randrange(-8, 40)])
                y1 = y0 + rng.choice([0, 1, 3, 5, rng.randrange(-4, 12)])
                cfg(9, (y1 & 0x1FF) << 16 | (x1 & 0x1FF) | rng.getrandbits(7) << 25 * (rng.random() < 0.2))
                cfg(8, y0 << 16 | x0 | rng.getrandbits(7) << 25 * (rng.random() < 0.2))
            elif r < 0.55:
                cfg(rng.choice([16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 0, 3, 7, 10, 26, rng.getrandbits(32)]), rng.getrandbits(32))
            elif r < 0.57:
                step(rst=1) if rng.random() < 0.5 else step(clear=1)
            else:
                for _ in range(rng.randrange(1, 12)):
                    step(gfx_op=1 if rng.random() < 0.9 else rng.randrange(2, 8))
        out.append(trace)
    return out
