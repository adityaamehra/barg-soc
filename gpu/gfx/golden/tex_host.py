"""Golden model of the texture memory's host window (block `tex_host`). Combinational. Never shown to the generator.

A host write (host_en & host_we) to 0x5000_0000 <= host_addr < 0x5000_0800 writes texels t = 2w and 2w + 1, w = host_addr bits 10:2
(halfword layout: texel t at byte 2t; the low half of host_wdata is the even texel). Texel (tx, ty), t = ty * 32 + tx, is in bank
(ty mod 2) * 2 + (tx mod 2) at index (ty >> 1) * 16 + (tx >> 1). So: t_we0 = t_we1 = hit & !host_addr[6], t_we2 = t_we3 = hit &
host_addr[6]; t_waddr = {host_addr[10:7], host_addr[5:2]} (8 bits); t_wdata_lo = host_wdata[15:0] (banks 0 and 2), t_wdata_hi =
host_wdata[31:16] (banks 1 and 3). t_waddr and the data are driven whether or not there is a write.
"""


def golden_tex_host(host_en, host_we, host_addr, host_wdata):
    hit = bool(host_en & 1 and host_we & 1 and 0x5000_0000 <= host_addr < 0x5000_0800)
    odd_row = host_addr >> 6 & 1
    return {"t_we0": int(hit and not odd_row), "t_we1": int(hit and not odd_row), "t_we2": int(hit and odd_row),
            "t_we3": int(hit and odd_row), "t_waddr": (host_addr >> 7 & 15) << 4 | (host_addr >> 2 & 15),
            "t_wdata_lo": host_wdata & 0xFFFF, "t_wdata_hi": host_wdata >> 16 & 0xFFFF}


def vectors(rng):
    out = []
    for _ in range(2000):
        r = rng.random()
        a = (0x5000_0000 + rng.randrange(0, 0x800) if r < 0.6 else rng.choice([0x5000_07FC, 0x5000_0800, 0x4FFF_FFFC, 0x5000_0000])
             if r < 0.75 else rng.getrandbits(32))
        out.append({"host_en": 1 if rng.random() < 0.85 else 0, "host_we": 1 if rng.random() < 0.8 else 0,
                    "host_addr": a, "host_wdata": rng.getrandbits(32)})
    return out
