"""Golden model of the tensor unit (block `tensor_unit`). Clocked, synchronous reset.

For each warp, a 4 x 4 accumulator ACC of 32-bit values (lane i owns row i). is_t = valid & (unit == TENSOR (5)).
Outputs (at once): err = is_t & (tmask != 1111). ld_y lane i = ACC[wid][i][a_i mod 4] (whatever the op).
At each rising edge: rst or clear_all sets every accumulator to 0. Otherwise when advance & is_t & !err, by tensor_op:
  0 mma.i8: ACC[wid][i][j] += sum over k of A[i][k] * B[k][j] (32-bit wrapping), where A[i][k] is byte k of a_i and
           B[k][j] is byte k of b_j, both signed 8-bit (byte k = bits 8k+7..8k).
  1 mma.ld: nothing changes. 2 mma.st: ACC[wid][i][b_i mod 4] = a_i for every lane i. 3 mma.zero: ACC[wid] = 0.
Before the first reset the accumulators are unknown.
"""

M = 0xFFFFFFFF


def _s8(v):
    v &= 0xFF
    return v - 256 if v & 0x80 else v


class Tensor:
    def __init__(self):
        self.acc = None

    def outputs(self, i):
        is_t = i["valid"] & 1 and i["unit"] == 5
        err = int(bool(is_t) and i["tmask"] & 15 != 15)
        if self.acc is None:
            return {"err": err, "ld_y": None}
        acc = self.acc[i["wid"] & 3]
        ld = sum(acc[k][(i["a"] >> 32 * k) & 3] << 32 * k for k in range(4))
        return {"err": err, "ld_y": ld}

    def edge(self, i):
        if i["rst"] & 1 or i["clear_all"] & 1:
            self.acc = [[[0] * 4 for _ in range(4)] for _ in range(4)]
            return
        if self.acc is None:
            return
        is_t = i["valid"] & 1 and i["unit"] == 5
        if not (i["advance"] & 1 and is_t) or i["tmask"] & 15 != 15:
            return
        acc, op = self.acc[i["wid"] & 3], i["tensor_op"] & 3
        lane = lambda v, k: v >> 32 * k & M  # noqa: E731
        if op == 0:
            A = [[_s8(lane(i["a"], r) >> 8 * k) for k in range(4)] for r in range(4)]
            B = [[_s8(lane(i["b"], c) >> 8 * k) for c in range(4)] for k in range(4)]
            for r in range(4):
                for c in range(4):
                    acc[r][c] = (acc[r][c] + sum(A[r][k] * B[k][c] for k in range(4))) & M
        elif op == 2:
            for r in range(4):
                acc[r][lane(i["b"], r) & 3] = lane(i["a"], r)
        elif op == 3:
            for r in range(4):
                acc[r] = [0, 0, 0, 0]


def golden_tensor_unit(trace):
    m, out = Tensor(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out


def traces(rng):
    """Directed traces: the unit is only exercised by a tensor instruction (valid, unit TENSOR) with every lane active and
    advance high, which random inputs almost never produce. Each trace resets, then mixes zero / st / mma / ld over the warps."""
    out = []
    for _ in range(30):
        trace = []
        for cycle in range(120):
            lane_vals = lambda bits: rng.getrandbits(bits)
            small = rng.random() < 0.5
            step = {"rst": 1 if cycle == 0 or rng.random() < 0.01 else 0, "clear_all": 1 if rng.random() < 0.02 else 0,
                    "valid": 1 if rng.random() < 0.95 else 0, "unit": 5 if rng.random() < 0.95 else rng.randrange(8),
                    "advance": 1 if rng.random() < 0.85 else 0, "tensor_op": rng.choice((0, 0, 0, 1, 2, 2, 3)),
                    "wid": rng.randrange(4), "tmask": 15 if rng.random() < 0.95 else rng.randrange(16),
                    "a": lane_vals(128), "b": lane_vals(128)}
            if small:     # small column indexes and bytes make st / ld hit the same entries and mma stay readable
                step["b"] = sum(rng.randrange(4) << 32 * i for i in range(4)) if step["tensor_op"] == 2 else step["b"]
            trace.append(step)
        out.append(trace)
    return out
