"""Golden model of the 4-lane iterative divider (block `vdiv`). Clocked, synchronous reset.

start = valid & (unit == DIV (2)). States IDLE, BUSY, DONE and a 5-bit count.
ready = 1 exactly in DONE; y = the four results in DONE, else 0.
At each rising edge: rst or clear: IDLE. IDLE with start: the operands a, b and md_op are taken, count = 0, BUSY.
BUSY: when count is 31, DONE; otherwise count + 1 (so BUSY lasts exactly 32 cycles). DONE with advance: IDLE.
Lane i result (RISC-V M): md_op 0 DIV (signed, rounding toward zero; x / 0 = all ones; -2^31 / -1 = -2^31),
1 DIVU (x / 0 = all ones), 2 REM (sign of the dividend; x rem 0 = x; -2^31 rem -1 = 0), 3 REMU (x remu 0 = x).
"""

M = 0xFFFFFFFF


def _s(x):
    return x - (1 << 32) if x >> 31 else x


def lane_result(op, x, z):
    sx, sz = _s(x), _s(z)
    if op == 0:
        if z == 0:
            return M
        if sx == -(1 << 31) and sz == -1:
            return x
        q = abs(sx) // abs(sz)
        return (q if (sx < 0) == (sz < 0) else -q) & M
    if op == 1:
        return M if z == 0 else x // z
    if op == 2:
        if z == 0:
            return x
        if sx == -(1 << 31) and sz == -1:
            return 0
        r = abs(sx) % abs(sz)
        return (r if sx >= 0 else -r) & M
    return x if z == 0 else x % z


class VDiv:
    def __init__(self):
        self.st, self.count, self.res = None, 0, 0

    def outputs(self, i):
        if self.st is None:
            return {"ready": None, "y": None}
        return {"ready": int(self.st == "DONE"), "y": self.res if self.st == "DONE" else 0}

    def edge(self, i):
        if i["rst"] & 1 or i["clear"] & 1:
            self.st = "IDLE"
            return
        if self.st == "IDLE" and i["valid"] & 1 and i["unit"] == 2:
            self.res = sum(lane_result(i["md_op"] & 3, i["a"] >> 32 * k & M, i["b"] >> 32 * k & M) << 32 * k
                           for k in range(4))
            self.st, self.count = "BUSY", 0
        elif self.st == "BUSY":
            if self.count == 31:
                self.st = "DONE"
            else:
                self.count += 1
        elif self.st == "DONE" and i["advance"] & 1:
            self.st = "IDLE"


def golden_vdiv(trace):
    m, out = VDiv(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out


EDGE = (0, 1, 2, 3, 4, 5, 7, 16, 31, 100, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFE, 0xFFFFFFFF, 0x12345678)


def traces(rng):
    """Directed traces: a division as the pipeline issues it: the operands held steady (small and edge values, so that
    quotients and remainders are small, zero, negative or overflowing) from the start until the result is taken, `advance`
    pulsed when done, then the next division. Random traces change the operands every cycle, which no pipeline does."""
    out = []
    for _ in range(40):
        trace = [{"rst": 1, "clear": 0, "valid": 0, "unit": 0, "md_op": 0, "a": 0, "b": 0, "advance": 0}]
        for _ in range(4):
            a = sum(rng.choice(EDGE) << 32 * i for i in range(4))
            b = sum(rng.choice(EDGE) << 32 * i for i in range(4))
            md = rng.randrange(4)
            for cycle in range(35):                       # start, 32 busy cycles, done (advance on the last)
                trace.append({"rst": 0, "clear": 0, "valid": 1, "unit": 2, "md_op": md, "a": a, "b": b,
                              "advance": 1 if cycle == 34 else 0})
            trace.append({"rst": 0, "clear": 1 if rng.random() < 0.2 else 0, "valid": 0, "unit": 0, "md_op": 0, "a": 0, "b": 0,
                          "advance": 0})
        out.append(trace)
    return out

