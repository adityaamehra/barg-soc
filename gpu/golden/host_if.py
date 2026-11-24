"""Golden model of the host interface (block `host_if`). Clocked, synchronous reset.

The host bus: host_en, host_we, host_addr, host_wdata in; host_rdata and host_rvalid out. A read's data comes in the cycle
after the request, with host_rvalid = 1. Control registers (host_addr): 0x3000_0000 CTRL (write bit 0 = 1 to start),
0x3000_0004 START_PC, 0x3000_0008 KARG, 0x3000_000C STATUS (bit 0 running, bit 1 done, bit 2 error), 0x3000_0010 ERR_PC,
0x3000_0014 ERR_INFO (bits 3:0 cause, bits 9:8 warp).
start (at once) = host_en & host_we & host_addr == CTRL & host_wdata bit 0 & !running.
Outputs: running, start, start_pc, karg (the registers' values).
Errors: at an edge with advance = 1, the first of err_illegal (cause 1), err_mem (2), err_simt (3), err_tensor (4),
err_csr (5) that is 1 is the cause.
At each rising edge: rst: every register 0. Otherwise:
  a host write (host_en & host_we, running 0) to START_PC or KARG stores host_wdata there.
  start: running 1, done 0, error 0.
  else, running and advance and a cause: running 0, error 1, ERR_PC = x_pc, ERR_INFO = cause | x_wid << 8.
  else, running and busy 0: running 0, done 1.
  rvalid becomes host_en & !host_we, and raddr becomes host_addr.
host_rdata (at once, from the address registered at the last edge, meaningful when host_rvalid is 1): in 0x1000_0000 ..
0x1000_1FFF the word of global bank (raddr >> 2) & 3 from g_rdata; in 0x2000_0000 .. 0x2000_0FFF the same from s_rdata;
a control register's present value; anything else 0.
"""

M = 0xFFFFFFFF


class HostIf:
    def __init__(self):
        self.r = None

    def _start(self, i):
        return int(bool(i["host_en"] & 1 and i["host_we"] & 1 and i["host_addr"] & M == 0x3000_0000
                        and i["host_wdata"] & 1 and not self.r["running"]))

    def outputs(self, i):
        if self.r is None:
            return {k: None for k in ("running", "start", "start_pc", "karg", "host_rdata", "host_rvalid", "done", "error")}
        r = self.r
        a = r["raddr"]
        if 0x1000_0000 <= a < 0x1000_2000:
            data = i["g_rdata"] >> 32 * (a >> 2 & 3) & M
        elif 0x2000_0000 <= a < 0x2000_1000:
            data = i["s_rdata"] >> 32 * (a >> 2 & 3) & M
        else:
            data = {0x3000_0004: r["start_pc"], 0x3000_0008: r["karg"],
                    0x3000_000C: r["running"] | r["done"] << 1 | r["error"] << 2,
                    0x3000_0010: r["err_pc"], 0x3000_0014: r["err_info"]}.get(a, 0)
        return {"running": r["running"], "start": self._start(i), "start_pc": r["start_pc"], "karg": r["karg"],
                "host_rdata": data, "host_rvalid": r["rvalid"], "done": r["done"], "error": r["error"]}

    def edge(self, i):
        if i["rst"] & 1:
            self.r = {k: 0 for k in ("running", "done", "error", "start_pc", "karg", "err_pc", "err_info", "rvalid", "raddr")}
            return
        if self.r is None:
            return
        r, a = dict(self.r), i["host_addr"] & M
        start = self._start(i)
        if i["host_en"] & 1 and i["host_we"] & 1 and not self.r["running"]:
            if a == 0x3000_0004:
                r["start_pc"] = i["host_wdata"] & M
            elif a == 0x3000_0008:
                r["karg"] = i["host_wdata"] & M
        cause = next((c for c, name in enumerate(("err_illegal", "err_mem", "err_simt", "err_tensor", "err_csr"), 1)
                      if i[name] & 1), 0)
        if start:
            r.update(running=1, done=0, error=0)
        elif self.r["running"] and i["advance"] & 1 and cause:
            r.update(running=0, error=1, err_pc=i["x_pc"] & M, err_info=cause | (i["x_wid"] & 3) << 8)
        elif self.r["running"] and not i["busy"] & 1:
            r.update(running=0, done=1)
        r["rvalid"] = int(bool(i["host_en"] & 1 and not i["host_we"] & 1))
        r["raddr"] = a
        self.r = r


def golden_host_if(trace):
    m, out = HostIf(), []
    for step in trace:
        out.append(m.outputs(step))
        m.edge(step)
    return out


def traces(rng):
    """Directed traces: host writes and reads at the control registers and inside global and shared memory, a start, and the
    core's finishing (busy low) or faulting (an error input with advance), so that every register, status bit and error cause
    is reached. Random 32-bit addresses never hit a control register."""
    regs = [0x3000_0000, 0x3000_0004, 0x3000_0008, 0x3000_000C, 0x3000_0010, 0x3000_0014]
    out = []
    for _ in range(40):
        trace = []
        for cycle in range(160):
            r = rng.random()
            addr = (rng.choice(regs) if r < 0.6 else
                    0x1000_0000 + (rng.randrange(0x2000) & ~3) if r < 0.75 else
                    0x2000_0000 + (rng.randrange(0x1000) & ~3) if r < 0.9 else rng.getrandbits(32))
            errs = {name: 1 if rng.random() < 0.04 else 0 for name in
                    ("err_illegal", "err_mem", "err_simt", "err_tensor", "err_csr")}
            step = {"rst": 1 if cycle == 0 or rng.random() < 0.01 else 0, "host_en": 1 if rng.random() < 0.7 else 0,
                    "host_we": rng.randrange(2), "host_addr": addr,
                    "host_wdata": rng.choice((0, 1, 1, 0xFFFFFFFF, rng.getrandbits(32))),
                    "busy": 1 if rng.random() < 0.8 else 0, "advance": 1 if rng.random() < 0.5 else 0,
                    "x_pc": rng.getrandbits(32) & ~3, "x_wid": rng.randrange(4),
                    "g_rdata": rng.getrandbits(128), "s_rdata": rng.getrandbits(128), **errs}
            trace.append(step)
        out.append(trace)
    return out
