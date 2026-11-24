"""Golden model of the four-context interrupt controller (block `plic4`). Clocked. Written by hand.

Sources 1..3 are level inputs s1..s3. Contexts 0..3 are the four harts' machine external interrupts. Registers, all 0 at reset:
prio[1..3] (3 bits each), enable[c] (bit s set when source s is enabled for context c), threshold[c] (3 bits), in_service[1..3] (1 bit).
Word offsets (off = bits 25:2 of addr, 24 bits; the rest of addr is ignored): 1..3 priority of source off; 0x400 pending (bit s = s_s and not in_service[s]); 0x800 + 0x20*c enable of
context c (bit s); 0x80000 + 0x400*c threshold of context c; 0x80001 + 0x400*c claim (read) / complete (write) of context c.
eligible(c, s) = s_s and not in_service[s] and enable[c] bit s and prio[s] > threshold[c]. claim(c) = the eligible source with the
highest priority (lowest number on a tie), or 0 when none is eligible.
Outputs, before the edge: rdata is the register at off as held (the claim word gives claim(c)); meip<c> is 1 when claim(c) is nonzero.
At each edge: reset sets everything to 0. Otherwise: a write (we) to off 1..3 sets prio; to the enable word of c sets enable[c] to
wdata bits 3:1; to the threshold word of c sets threshold[c] to wdata bits 2:0; to the claim word of c with wdata 1..3 clears
in_service[wdata]. A read (re) of the claim word of c with claim(c) nonzero sets in_service[claim(c)]. At most one of we and re is 1.
Before the first reset: outputs None."""

M = 0xFFFFFFFF


def _eligible(st, ins, c):
    best = 0
    for s in (1, 2, 3):
        if ins[f"s{s}"] & 1 and not st["ins"][s] and (st["en"][c] >> s) & 1 and st["prio"][s] > st["thr"][c]:
            if best == 0 or st["prio"][s] > st["prio"][best]:
                best = s
    return best


def _word(st, ins, off):
    if off in (1, 2, 3):
        return st["prio"][off]
    if off == 0x400:
        return sum(((ins[f"s{s}"] & 1) and not st["ins"][s]) << s for s in (1, 2, 3))
    for c in range(4):
        if off == 0x800 + 0x20 * c:
            return st["en"][c]
        if off == 0x80000 + 0x400 * c:
            return st["thr"][c]
        if off == 0x80001 + 0x400 * c:
            return _eligible(st, ins, c)
    return 0


def golden_plic4(trace):
    st = None
    out = []
    for ins in trace:
        ins = {**ins, "off": (ins["addr"] >> 2) & 0xFFFFFF}
        if st is None:
            out.append({"rdata": None, **{f"meip{c}": None for c in range(4)}})
        else:
            out.append({"rdata": _word(st, ins, ins["off"]) & M,
                        **{f"meip{c}": int(_eligible(st, ins, c) != 0) for c in range(4)}})
        if ins["rst"] & 1:
            st = {"prio": {1: 0, 2: 0, 3: 0}, "en": [0, 0, 0, 0], "thr": [0, 0, 0, 0], "ins": {1: 0, 2: 0, 3: 0}}
            continue
        if st is None:
            continue
        off = ins["off"]
        if ins["we"] & 1:
            if off in (1, 2, 3):
                st["prio"][off] = ins["wdata"] & 7
            for c in range(4):
                if off == 0x800 + 0x20 * c:
                    st["en"][c] = ((ins["wdata"] >> 1) & 7) << 1
                if off == 0x80000 + 0x400 * c:
                    st["thr"][c] = ins["wdata"] & 7
                if off == 0x80001 + 0x400 * c and ins["wdata"] in (1, 2, 3):
                    st["ins"][ins["wdata"]] = 0
        elif ins["re"] & 1:
            for c in range(4):
                if off == 0x80001 + 0x400 * c:
                    e = _eligible(st, ins, c)
                    if e:
                        st["ins"][e] = 1
    return out


def traces(rng):
    out = []
    for _ in range(40):
        t = [{"rst": 1, "we": 0, "re": 0, "addr": 0, "wdata": 0, "s1": 0, "s2": 0, "s3": 0}]
        offs = [1, 2, 3, 0x400, 0x800, 0x820, 0x840, 0x860, 0x80000, 0x80400, 0x80800, 0x80C00, 0x80001, 0x80401, 0x80801, 0x80C01]
        for _ in range(150):
            we = int(rng.random() < 0.3)
            re = int(not we and rng.random() < 0.3)
            t.append({"rst": int(rng.random() < 0.01), "we": we, "re": re, "addr": (rng.choice(offs) << 2) | (rng.getrandbits(6) << 26) | rng.getrandbits(2) * 0,
                      "wdata": rng.choice([rng.getrandbits(32), rng.randrange(8), rng.randrange(16), 0]),
                      "s1": int(rng.random() < 0.4), "s2": int(rng.random() < 0.3), "s3": int(rng.random() < 0.3)})
        out.append(t)
    return out
