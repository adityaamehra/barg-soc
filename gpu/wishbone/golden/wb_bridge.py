"""Golden model of the Wishbone-to-host-bus bridge (block `wb_bridge`). Clocked, synchronous reset.

Registers (0 at reset): state (IDLE 0, REQ 1, WAIT 2, DONE 3), we_r, addr_r (32), wdata_r (32), rdata_r (32).
Outputs (all from registers, none depends on a same-cycle input): host_en = state == REQ; host_we = state == REQ and we_r;
host_addr = addr_r; host_wdata = wdata_r; wb_ack = state == DONE; wb_dat_o = rdata_r.
At each rising edge: rst: everything 0. Otherwise by state:
  IDLE: when wb_cyc and wb_stb: we_r = wb_we, wdata_r = wb_dat_i, rdata_r = 0, and the address is decoded. Valid = wb_adr bits
        31:20 are 0x300 and bits 1:0 are 0. Window = bits 19:16: 0 control (any offset), 1 instruction
        memory (bits 15:11 zero), 2 global memory (bits 15:13 zero), 3 shared memory (bits 15:12 zero); any other window is
        unmapped. host address: control 0x3000_0000 | bits 15:0; instruction memory bits 10:0; global 0x1000_0000 | bits 12:0;
        shared 0x2000_0000 | bits 11:0. A read of a mapped address goes to REQ, and so does a write of a mapped address when
        wb_sel is 1111; every other access (unmapped, misaligned, a write with wb_sel not 1111) is dropped: addr_r keeps its
        value and the state goes to DONE with rdata_r = 0.
  REQ:  a write goes to DONE; a read goes to WAIT.
  WAIT: when host_rvalid: rdata_r = host_rdata and DONE.
  DONE: IDLE.
The control window maps every offset bits 15:0 to host address 0x3000_0000 + offset (the host interface ignores the ones it
does not have). Before the first reset the registers are unknown.
"""

M = 0xFFFFFFFF
IDLE, REQ, WAIT, DONE = range(4)


class Bridge:
    def __init__(self):
        self.s = None

    def outputs(self, i):
        s = self.s
        if s is None:
            return {k: None for k in ("wb_ack", "wb_dat_o", "host_en", "host_we", "host_addr", "host_wdata")}
        return {"wb_ack": int(s["state"] == DONE), "wb_dat_o": s["rdata"], "host_en": int(s["state"] == REQ),
                "host_we": int(s["state"] == REQ and s["we"]), "host_addr": s["addr"], "host_wdata": s["wdata"]}

    def edge(self, i):
        if i["rst"] & 1:
            self.s = {"state": IDLE, "we": 0, "addr": 0, "wdata": 0, "rdata": 0}
            return
        s = self.s
        if s is None:
            return
        if s["state"] == IDLE:
            if i["wb_cyc"] & 1 and i["wb_stb"] & 1:
                adr, we = i["wb_adr"] & M, i["wb_we"] & 1
                s["we"], s["wdata"], s["rdata"] = we, i["wb_dat_i"] & M, 0
                host = decode(adr)
                if host is not None and (not we or i["wb_sel"] & 15 == 15):
                    s["addr"], s["state"] = host, REQ
                else:
                    s["state"] = DONE
        elif s["state"] == REQ:
            s["state"] = WAIT if not s["we"] else DONE
        elif s["state"] == WAIT:
            if i["host_rvalid"] & 1:
                s["rdata"], s["state"] = i["host_rdata"] & M, DONE
        else:
            s["state"] = IDLE


def decode(adr):
    """The host-bus address for a Wishbone address, or None when it is not a mapped word."""
    if adr >> 20 != 0x300 or adr & 3:
        return None
    window, off = adr >> 16 & 15, adr & 0xFFFF
    if window == 0:
        return 0x30000000 | off
    if window == 1 and off >> 11 == 0:
        return off
    if window == 2 and off >> 13 == 0:
        return 0x10000000 | off
    if window == 3 and off >> 12 == 0:
        return 0x20000000 | off
    return None


def golden_wb_bridge(trace):
    m, out = Bridge(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out


def _addr(rng):
    """A Wishbone address: mostly mapped words in every window, a few misaligned, past a window's end, unmapped or outside."""
    if rng.random() < 0.05:
        return rng.getrandbits(32)
    window = rng.choice([0, 1, 2, 3, 3, 2, 1, 2, 3, 4, 15] if rng.random() < 0.95 else [4, 5, 15])
    span = {0: 0x20, 1: 0x800, 2: 0x2000, 3: 0x1000}.get(window, 0x1000)
    off = rng.randrange(0, 2 * span if rng.random() < 0.1 else span) & ~3
    if rng.random() < 0.08:
        off |= rng.randrange(1, 4)
    adr = 0x30000000 | window << 16 | off
    if rng.random() < 0.04:
        adr |= rng.choice([0x100000, 0x1000000, 0x80000000])
    return adr & M


def traces(rng):
    """Directed traces: a Wishbone master that holds cyc and stb until it sees ack, sometimes idles between transfers, and
    a host bus that answers a read one cycle after the request with fresh data (as host_if does); some traces instead
    answer late, never or at random."""
    out = []
    for n in range(60):
        mode = n % 4                                  # 0 prompt host, 1 late host, 2 noise on host_rvalid, 3 prompt with back-to-back
        trace, m = [], Bridge()
        pending = []                                  # host reads in flight: (cycles left, data)
        want = None                                   # the transfer the master holds
        idle = 0

        def step(**kw):
            base = {"rst": 0, "wb_cyc": 0, "wb_stb": 0, "wb_we": 0, "wb_sel": 0, "wb_adr": 0, "wb_dat_i": 0, "host_rdata": 0,
                    "host_rvalid": 0}
            base.update(kw)
            trace.append(base)
            return base

        for cycle in range(3):
            m.edge(step(rst=1 if cycle < 2 else 0))
            if cycle < 2:
                continue
        for _ in range(rng.randrange(50, 110)):
            if want is None and idle == 0:
                want = {"adr": _addr(rng), "we": rng.random() < 0.5, "sel": 15 if rng.random() < 0.85 else rng.randrange(16),
                        "dat": rng.getrandbits(32)}
            if want is not None and idle > 0:
                idle -= 1
            drive = dict(wb_cyc=1, wb_stb=1, wb_we=int(want["we"]), wb_sel=want["sel"], wb_adr=want["adr"],
                         wb_dat_i=want["dat"]) if want is not None and idle == 0 else {}
            rvalid, rdata = 0, rng.getrandbits(32)
            if mode == 2:
                rvalid = int(rng.random() < 0.3)
            elif pending:
                pending = [(c - 1, d) for c, d in pending]
                due = [d for c, d in pending if c <= 0]
                pending = [(c, d) for c, d in pending if c > 0]
                if due:
                    rvalid, rdata = 1, due[0]
            cur = step(**drive, host_rvalid=rvalid, host_rdata=rdata)
            o = m.outputs(cur)
            if o["host_en"] and not o["host_we"] and mode != 2:
                pending.append((1 if mode != 1 else 1 + rng.randrange(0, 4), rng.getrandbits(32)))
            m.edge(cur)
            if o["wb_ack"] and want is not None:
                want, idle = None, (0 if mode == 3 else rng.randrange(0, 3))
        out.append(trace)
    return out
