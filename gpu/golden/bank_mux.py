"""Golden model of the memory-port switch (block `bank_mux`). Combinational.

While running is 1 the load-store unit owns the eight banks: global bank k gets we = g_en_k & g_we_k, addr, wdata and be from
field k of the packed g_ ports (layout as in lsu), and likewise shared bank k from the s_ ports; the instruction memory's
write port is off (imem_we 0; imem_waddr and imem_wdata are don't-care whenever imem_we is 0).
While running is 0 the host owns them, one 32-bit word at a time: for host_addr in 0x0000_0000..0x0000_07FF: imem_we =
host_en & host_we, imem_waddr = bits 10:2, imem_wdata = host_wdata. In 0x1000_0000..0x1000_1FFF: global bank
(host_addr >> 2) & 3 gets addr = (host_addr - 0x1000_0000) >> 4, we = host_en & host_we, wdata = host_wdata, be = 1111. In
0x2000_0000..0x2000_0FFF: shared bank (host_addr >> 2) & 3 the same way, addr = (host_addr - 0x2000_0000) >> 4.
While running is 0, every bank the host is not addressing has we 0 and its addr, wdata and be are don't-care (None). Always: g_rdata packs the four global banks' rdata (bank k in bits
32k+31..32k), s_rdata the four shared banks'.
"""

M = 0xFFFFFFFF


def golden_bank_mux(running, g_en, g_we, g_addr, g_wdata, g_be, s_en, s_we, s_addr, s_wdata, s_be,
                    host_en, host_we, host_addr, host_wdata,
                    gb0_rdata, gb1_rdata, gb2_rdata, gb3_rdata, sb0_rdata, sb1_rdata, sb2_rdata, sb3_rdata):
    o = {}
    for sp in ("g", "s"):
        for k in range(4):
            o.update({f"{sp}b{k}_we": 0, f"{sp}b{k}_addr": 0, f"{sp}b{k}_wdata": 0, f"{sp}b{k}_be": 0})
    o.update(imem_we=0, imem_waddr=0, imem_wdata=0)
    if running & 1:
        for sp, en, we, addr, wdata, be, wb in (("g", g_en, g_we, g_addr, g_wdata, g_be, 9), ("s", s_en, s_we, s_addr, s_wdata, s_be, 8)):
            for k in range(4):
                o[f"{sp}b{k}_we"] = (en >> k & 1) & (we >> k & 1)
                o[f"{sp}b{k}_addr"] = addr >> wb * k & ((1 << wb) - 1)
                o[f"{sp}b{k}_wdata"] = wdata >> 32 * k & M
                o[f"{sp}b{k}_be"] = be >> 4 * k & 15
    else:
        w = (host_en & 1) & (host_we & 1)
        a = host_addr & M
        sel = None                                # the bank the host addresses, if any
        if 0x1000_0000 <= a < 0x1000_2000:
            sel = ("g", a >> 2 & 3)
        elif 0x2000_0000 <= a < 0x2000_1000:
            sel = ("s", a >> 2 & 3)
        for k in range(4):                        # a bank the host is not addressing: only we (0) is defined
            for sp in ("g", "s"):
                if sel != (sp, k):
                    o[f"{sp}b{k}_addr"] = o[f"{sp}b{k}_wdata"] = o[f"{sp}b{k}_be"] = None
        if a < 0x800:
            o.update(imem_we=w, imem_waddr=a >> 2 & 511, imem_wdata=host_wdata & M)
        elif 0x1000_0000 <= a < 0x1000_2000:
            k = a >> 2 & 3
            o.update({f"gb{k}_we": w, f"gb{k}_addr": (a - 0x1000_0000) >> 4, f"gb{k}_wdata": host_wdata & M, f"gb{k}_be": 15})
        elif 0x2000_0000 <= a < 0x2000_1000:
            k = a >> 2 & 3
            o.update({f"sb{k}_we": w, f"sb{k}_addr": (a - 0x2000_0000) >> 4, f"sb{k}_wdata": host_wdata & M, f"sb{k}_be": 15})
    if not o["imem_we"]:
        o["imem_waddr"] = o["imem_wdata"] = None
    g = [gb0_rdata, gb1_rdata, gb2_rdata, gb3_rdata]
    s = [sb0_rdata, sb1_rdata, sb2_rdata, sb3_rdata]
    o["g_rdata"] = sum((g[k] & M) << 32 * k for k in range(4))
    o["s_rdata"] = sum((s[k] & M) << 32 * k for k in range(4))
    return o


def vectors(rng):
    """Directed vectors: host addresses inside each region (every bank of global and shared memory, both modes, with and
    without host_en / host_we), plus load-store-mode vectors. Random 32-bit addresses almost never fall in an 8 KB window."""
    out = []
    bases = [0x0000_0000, 0x1000_0000, 0x2000_0000]
    spans = [0x800, 0x2000, 0x1000]
    for _ in range(300):
        r = rng.randrange(3)
        addr = bases[r] + (rng.randrange(spans[r]) & ~3)
        out.append(_vec(rng, running=0, host_addr=addr, host_en=rng.randrange(2), host_we=rng.randrange(2)))
    for _ in range(40):                                                  # around the edges of each window
        r = rng.randrange(3)
        edge = rng.choice((-4, 0, 4, spans[r] - 4, spans[r], spans[r] + 4))
        out.append(_vec(rng, running=0, host_addr=(bases[r] + edge) & 0xFFFFFFFF, host_en=1, host_we=rng.randrange(2)))
    for _ in range(100):
        out.append(_vec(rng, running=1, host_addr=rng.choice(bases) + (rng.randrange(0x800) & ~3), host_en=1, host_we=1))
    return out


def _vec(rng, **kw):
    v = {"g_en": rng.randrange(16), "g_we": rng.randrange(16), "g_addr": rng.getrandbits(36), "g_wdata": rng.getrandbits(128),
         "g_be": rng.getrandbits(16), "s_en": rng.randrange(16), "s_we": rng.randrange(16), "s_addr": rng.getrandbits(32),
         "s_wdata": rng.getrandbits(128), "s_be": rng.getrandbits(16), "host_wdata": rng.getrandbits(32)}
    for k in range(4):
        v[f"gb{k}_rdata"] = rng.getrandbits(32)
        v[f"sb{k}_rdata"] = rng.getrandbits(32)
    v.update(kw)
    return v
