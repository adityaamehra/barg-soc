"""Golden model of the load-store unit (block `lsu`). Clocked, synchronous reset.

Global memory is 4 banks of 512 32-bit words, shared memory 4 banks of 256; bank k holds the words whose address bits 3:2
are k. Packed bank ports: bank k's field of g_en/g_we/s_en/s_we is bit k, of g_addr bits 9k+8..9k, of s_addr 8k+7..8k, of
g_wdata/s_wdata/g_rdata/s_rdata bits 32k+31..32k, of g_be/s_be bits 4k+3..4k. A bank's rdata shows the word addressed in
the cycle before (synchronous read).

act = valid & (unit == LSU (3)). Lane i's address A_i = a_i + imm (32 bits); bytes n = 1 for mem_size 0 and 4, 2 for 1 and
5, 4 for 2. Lane i is in global memory when 0x1000_0000 <= A_i < 0x1000_2000 (word index (A_i - 0x1000_0000) >> 4), in
shared when 0x2000_0000 <= A_i < 0x2000_1000 (word index (A_i - 0x2000_0000) >> 4); bank (A_i >> 2) & 3; offset A_i & 3.
err = act & !started & (some active lane (tmask) has A_i % n != 0 or is in neither memory).

State: started, pend (lanes still to access), got (lanes whose load data arrives this cycle), cap (128 bits).
P = tmask when started is 0, else pend. Requests (only when act & !err): for each memory and bank, the lowest-numbered lane in
P mapped to it is chosen; its bank gets en = 1, we = mem_store, addr = its word index, wdata = b_i << 8 * offset (32 bits),
be = ((1 << n) - 1) << offset. Other banks: every field 0.
Load data: cur = cap with each lane in got replaced by its bytes from its bank's rdata (n bytes at its offset, sign-extended
for mem_size 0 and 1, zero-extended otherwise). y = cur.
ready = act & (err | (mem_store & every lane of P is chosen now) | (!mem_store & started & P == 0)).
At each rising edge: rst: started = 0, pend = 0, got = 0 and cap = 0; clear or advance: started = 0, pend = 0, got = 0. Otherwise when act & !err: started = 1,
pend = P minus the chosen lanes, got = the chosen lanes when loading (0 when storing), cap = cur.
"""

M = 0xFFFFFFFF


class Lsu:
    def __init__(self):
        self.started = None
        self.pend = self.got = self.cap = 0

    def _decode(self, i):
        size = i["mem_size"] & 7
        n = {0: 1, 4: 1, 1: 2, 5: 2}.get(size, 4)
        lanes = []
        for k in range(4):
            A = ((i["a"] >> 32 * k & M) + i["imm"]) & M
            if 0x1000_0000 <= A < 0x1000_2000:
                space, idx = "g", (A - 0x1000_0000) >> 4
            elif 0x2000_0000 <= A < 0x2000_1000:
                space, idx = "s", (A - 0x2000_0000) >> 4
            else:
                space, idx = None, 0
            lanes.append((A, space, idx, A >> 2 & 3, A & 3, A % n != 0))
        return n, size, lanes

    def _comb(self, i):
        act = i["valid"] & 1 and i["unit"] == 3
        n, size, lanes = self._decode(i)
        tm = i["tmask"] & 15
        o = {"g_en": 0, "g_we": 0, "g_addr": 0, "g_wdata": 0, "g_be": 0,
             "s_en": 0, "s_we": 0, "s_addr": 0, "s_wdata": 0, "s_be": 0}
        if self.started is None:                  # before the first reset: nothing is known (don't-care)
            return {k: None for k in o} | {"ready": None, "y": None, "err": None}, 0, 0
        if not act:
            return o | {"ready": 0, "y": self.cap, "err": 0}, 0, 0
        err = not self.started and any(tm >> k & 1 and (lanes[k][1] is None or lanes[k][5]) for k in range(4))
        P = self.pend if self.started else tm
        chosen = 0
        store = i["mem_store"] & 1
        if not err:
            taken = set()
            for k in range(4):
                if P >> k & 1:
                    A, space, idx, bank, off, _ = lanes[k]
                    if (space, bank) in taken:
                        continue
                    taken.add((space, bank))
                    chosen |= 1 << k
                    wbits = 9 if space == "g" else 8
                    o[space + "_en"] |= 1 << bank
                    o[space + "_we"] |= store << bank
                    o[space + "_addr"] |= idx << wbits * bank
                    o[space + "_wdata"] |= ((i["b"] >> 32 * k & M) << 8 * off & M) << 32 * bank
                    o[space + "_be"] |= (((1 << n) - 1) << off & 15) << 4 * bank
        cur = self.cap
        for k in range(4):
            if self.got >> k & 1:
                A, space, idx, bank, off, _ = lanes[k]
                word = i[space + "_rdata"] >> 32 * bank & M
                v = word >> 8 * off & ((1 << 8 * n) - 1)
                if size in (0, 1) and v >> (8 * n - 1) & 1:
                    v = (v - (1 << 8 * n)) & M
                cur = cur & ~(M << 32 * k) | v << 32 * k
        ready = int(bool(err) or (store and (P & ~chosen) == 0) or (not store and self.started and P == 0))
        return o | {"ready": ready, "y": cur, "err": int(bool(err))}, chosen, cur

    def outputs(self, i):
        return self._comb(i)[0]

    def edge(self, i):
        if i["rst"] & 1:
            self.started, self.pend, self.got, self.cap = 0, 0, 0, 0
            return
        if i["clear"] & 1 or (self.started is not None and i["advance"] & 1):
            self.started, self.pend, self.got = 0, 0, 0
            return
        if self.started is None:
            return
        o, chosen, cur = self._comb(i)
        act = i["valid"] & 1 and i["unit"] == 3
        if act and not o["err"]:
            P = self.pend if self.started else i["tmask"] & 15
            self.started, self.pend = 1, P & ~chosen
            self.got = 0 if i["mem_store"] & 1 else chosen
            self.cap = cur


def golden_lsu(trace):
    m, out = Lsu(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out


def traces(rng):
    """Directed traces: load and store instructions (valid, unit LSU) with the lanes' addresses inside global or shared memory,
    aligned for the access size (and now and then not), all and some lanes active, several lanes mapped to one bank, and
    advance pulsed once the access has had time to finish. Random inputs almost never form an access inside an 8 KB window."""
    out = []
    for _ in range(40):
        trace = []
        held = None
        for cycle in range(160):
            if held is None or rng.random() < 0.15:           # a new instruction
                size = rng.choice((0, 1, 2, 4, 5))
                n = {0: 1, 4: 1, 1: 2, 5: 2}.get(size, 4)
                base = rng.choice((0x1000_0000, 0x2000_0000))
                span = 0x2000 if base == 0x1000_0000 else 0x1000
                same_bank = rng.random() < 0.4
                lanes = []
                for i in range(4):
                    off = rng.randrange(span // n) * n if rng.random() < 0.97 else rng.randrange(span)
                    if same_bank:
                        off = (off & ~0xF) | 8
                    elif rng.random() < 0.5:
                        off = (off & ~0xF) + 4 * i if n == 4 else off
                    lanes.append((base + off) & 0xFFFFFFFF)
                held = {"valid": 1, "unit": 3, "mem_store": rng.randrange(2), "mem_size": size,
                        "tmask": 15 if rng.random() < 0.6 else rng.randrange(16),
                        "a": sum(lane << 32 * i for i, lane in enumerate(lanes)), "imm": 0,
                        "b": rng.getrandbits(128)}
            step = dict(held)
            step.update(clear=1 if rng.random() < 0.02 else 0, advance=1 if rng.random() < 0.3 else 0,
                        g_rdata=rng.getrandbits(128), s_rdata=rng.getrandbits(128),
                        rst=1 if cycle == 0 or rng.random() < 0.01 else 0)
            if rng.random() < 0.1:
                step.update(valid=rng.randrange(2), unit=rng.randrange(8))
            trace.append(step)
        out.append(trace)
    return out
