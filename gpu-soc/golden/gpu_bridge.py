"""A golden model of the bridge from the SoC's memory stage to the GPU's host bus (block `gpu_bridge`). Clocked. Written by hand.

Window offset off = addr bits 23:0 (the region is 0x3000_0000..0x30FF_FFFF; region_decode selects it). Mapped ranges and the host
address each gives:
  0x00_0000..0x00_FFFF  control registers  0x3000_0000 | off[15:0]
  0x01_0000..0x01_07FF  instruction memory 0x0000_0000 | off[10:0]
  0x02_0000..0x02_1FFF  global memory      0x1000_0000 | off[12:0]
  0x03_0000..0x03_0FFF  shared memory      0x2000_0000 | off[11:0]
  0x10_0000..0x12_57FF  video memory       0x4000_0000 | off[17:0]
  0x14_0000..0x16_57FF  depth memory       0x4004_0000 | off[17:0]
  0x18_0000..0x18_07FF  texture            0x5000_0000 | off[10:0]
Anything else in the window is unmapped. Accesses are words: word = memtype is 2 (MEM_WORD) or 6 or 7 (reserved codes, as MEM_WORD).
Outputs at once: host_en = mapped & ((gpu_we & word) | gpu_re); host_we = mapped & gpu_we & word; host_addr = the host address
(0 when unmapped); host_wdata = wdata; rdata = host_rdata when host_rvalid is 1, else the register rdata_r.
Register rdata_r (32 bits): at a rising edge, rst sets it to 0; otherwise when host_rvalid is 1 it takes host_rdata. So a load
returns the value of the previous GPU read and starts its own, whose result is on host_rdata the next cycle and in rdata_r after
that: a driver reads twice, and two back-to-back loads (lw; lw) work.
"""

RANGES = [(0x00_0000, 0x01_0000, 0x3000_0000, 0xFFFF), (0x01_0000, 0x01_0800, 0x0000_0000, 0x7FF),
          (0x02_0000, 0x02_2000, 0x1000_0000, 0x1FFF), (0x03_0000, 0x03_1000, 0x2000_0000, 0xFFF),
          (0x10_0000, 0x12_5800, 0x4000_0000, 0x3FFFF), (0x14_0000, 0x16_5800, 0x4004_0000, 0x3FFFF),
          (0x18_0000, 0x18_0800, 0x5000_0000, 0x7FF)]


def translate(addr):
    off = addr & 0xFFFFFF
    for lo, hi, base, mask in RANGES:
        if lo <= off < hi:
            return True, base | (off & mask)
    return False, 0


class Bridge:
    def __init__(self):
        self.r = None

    def outputs(self, i):
        mapped, host = translate(i["addr"])
        word = i["memtype"] & 7 in (2, 6, 7)
        we = mapped and i["gpu_we"] & 1 and word
        return {"host_en": int(bool(we or (mapped and i["gpu_re"] & 1))), "host_we": int(bool(we)), "host_addr": host,
                "host_wdata": i["wdata"] & 0xFFFFFFFF,
                "rdata": (i["host_rdata"] & 0xFFFFFFFF) if i["host_rvalid"] & 1 else self.r}

    def edge(self, i):
        if i["rst"] & 1:
            self.r = 0
        elif self.r is not None and i["host_rvalid"] & 1:
            self.r = i["host_rdata"] & 0xFFFFFFFF


def golden_gpu_bridge(trace):
    m, out = Bridge(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out


def traces(rng):
    """Addresses in every window (at both ends, just past the end), unmapped holes, other regions' addresses (the strobes are 0
    there, as region_decode gives), every memtype, reads answered a cycle later as the host bus does, rst in between."""
    def addr():
        r = rng.random()
        if r < 0.75:
            lo, hi, _, _ = rng.choice(RANGES)
            off = rng.choice([lo, hi - 4, hi, rng.randrange(lo, hi)])
        else:
            off = rng.getrandbits(24)
        return 0x3000_0000 | off & ~3 if rng.random() < 0.9 else rng.getrandbits(32)
    out = []
    for _ in range(40):
        t, pending = [{"rst": 1, "gpu_we": 0, "gpu_re": 0, "addr": 0, "wdata": 0, "memtype": 5, "host_rdata": 0, "host_rvalid": 0}], False
        for _ in range(150):
            kind = rng.random()
            s = {"rst": 1 if rng.random() < 0.01 else 0, "gpu_we": int(kind < 0.4), "gpu_re": int(0.4 <= kind < 0.75),
                 "addr": addr(), "wdata": rng.getrandbits(32), "memtype": 2 if rng.random() < 0.8 else rng.randrange(8),
                 "host_rdata": rng.getrandbits(32), "host_rvalid": int(pending or rng.random() < 0.05)}
            pending = bool(s["gpu_re"])
            t.append(s)
        out.append(t)
    return out
