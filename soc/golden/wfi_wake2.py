"""Golden model of `wfi_wake2`: hold the pipeline at a WFI instruction until an enabled interrupt is pending, but give up after 65535 cycles of waiting
(a WFI may always return early; the cap also breaks the wait when the instruction that would make an interrupt pending is itself stuck behind the hold).
Clocked: held state cnt (16 bits), None before the first reset."""


def golden_wfi_wake2(trace):
    cnt = None
    out = []
    for i in trace:
        if cnt is None:
            out.append({"hold": None})
        else:
            pend = (i["mip_sw"] & 0xFFF) | ((i["msip"] & 1) << 3) | ((i["mtip"] & 1) << 7) | ((i["meip"] & 1) << 11)
            raw = i["inst"] == 0x10500073 and (pend & i["mie"] & 0xFFF) == 0
            out.append({"hold": int(raw and cnt != 0xFFFF)})
        if i["rst"] & 1:
            cnt = 0
        elif cnt is not None:
            pend = (i["mip_sw"] & 0xFFF) | ((i["msip"] & 1) << 3) | ((i["mtip"] & 1) << 7) | ((i["meip"] & 1) << 11)
            raw = i["inst"] == 0x10500073 and (pend & i["mie"] & 0xFFF) == 0
            cnt = (cnt if cnt == 0xFFFF else cnt + 1) if raw else 0
    return out


def traces(rng):
    out = []
    for _ in range(40):                       # short random traces
        t = [{"rst": 1, "inst": 0, "msip": 0, "mtip": 0, "meip": 0, "mip_sw": 0, "mie": 0}]
        for _ in range(300):
            wfi = rng.random() < 0.8
            t.append({"rst": int(rng.random() < 0.01), "inst": 0x10500073 if wfi else rng.choice([0x13, rng.getrandbits(32)]),
                      "msip": int(rng.random() < 0.05), "mtip": int(rng.random() < 0.05), "meip": int(rng.random() < 0.05),
                      "mip_sw": rng.getrandbits(12) if rng.random() < 0.1 else 0, "mie": rng.getrandbits(12) if rng.random() < 0.5 else 0})
        out.append(t)
    for n in (70000, 140000):                 # long waits: the cap is reached, the hold drops, a new WFI starts a new wait
        t = [{"rst": 1, "inst": 0, "msip": 0, "mtip": 0, "meip": 0, "mip_sw": 0, "mie": 0}]
        for c in range(n):
            t.append({"rst": 0, "inst": 0x10500073 if (c % 90000) < 80000 else 0x13, "msip": 0, "mtip": 0, "meip": 0, "mip_sw": 0, "mie": 0x888 if c % 70001 == 70000 else 0})
        out.append(t)
    return out
