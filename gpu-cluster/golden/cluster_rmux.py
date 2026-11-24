"""Golden model of the read-data multiplexer of the GPU cluster (block `cluster_rmux`). Clocked. Written by hand.

A core answers a read one cycle after the request, so the multiplexer remembers which core the request was for: the register
slot_r (4 bits) takes `slot` at each rising edge when host_en is 1 and host_we is 0 (a read request), becomes 0 on rst, and keeps its
value otherwise. The core read is sel = slot_r, except slot_r = 15 (a broadcast, which has no one answer) reads core 0. rdata and
rvalid are rdata<sel> and rvalid<sel> for sel 0..9, and 0 and 0 for sel 10..14.
"""

N = 10


def golden_cluster_rmux(trace):
    r, out = None, []
    for s in trace:
        if r is None:
            out.append({"rdata": None, "rvalid": None})
        else:
            sel = 0 if r == 15 else r
            out.append({"rdata": s[f"rdata{sel}"] & 0xFFFFFFFF if sel < N else 0, "rvalid": s[f"rvalid{sel}"] & 1 if sel < N else 0})
        if s["rst"] & 1:
            r = 0
        elif s["host_en"] & 1 and not s["host_we"] & 1:
            r = s["slot"] & 0xF
    return out


def traces(rng):
    out = []
    for _ in range(40):
        t = [{"rst": 1, "host_en": 0, "host_we": 0, "slot": 0, **{f"rdata{i}": 0 for i in range(N)}, **{f"rvalid{i}": 0 for i in range(N)}}]
        for _ in range(120):
            t.append({"rst": int(rng.random() < 0.01), "host_en": rng.getrandbits(1), "host_we": rng.getrandbits(1),
                      "slot": rng.getrandbits(4) if rng.random() < 0.5 else rng.randrange(11),
                      **{f"rdata{i}": rng.getrandbits(32) for i in range(N)}, **{f"rvalid{i}": rng.getrandbits(1) for i in range(N)}})
        out.append(t)
    return out
