"""Golden model of the depth memory's host window (block `z_host`). Combinational, write only. Never shown to the generator.

A host write (host_en & host_we) to 0x4004_0000 <= host_addr < 0x4006_5800 sets depth pixels 2w (low half of host_wdata) and 2w + 1
(high half), w = (host_addr - 0x4004_0000) >> 2; pixel p is in bank p mod 4 at index p >> 2. So zh_we0 = zh_we1 = hit & (host_addr
bit 2 is 0), zh_we2 = zh_we3 = hit & (host_addr bit 2 is 1); zh_waddr = host_addr bits 17:3 (15 bits); zh_wdata_lo = host_wdata
bits 15:0 (banks 0, 2), zh_wdata_hi = bits 31:16 (banks 1, 3). zh_waddr and the data follow the inputs whether or not there is a write.
"""


def golden_z_host(host_en, host_we, host_addr, host_wdata):
    hit = bool(host_en & 1 and host_we & 1 and 0x4004_0000 <= host_addr < 0x4006_5800)
    odd = host_addr >> 2 & 1
    return {"zh_we0": int(hit and not odd), "zh_we1": int(hit and not odd), "zh_we2": int(hit and odd), "zh_we3": int(hit and odd),
            "zh_waddr": host_addr >> 3 & 0x7FFF, "zh_wdata_lo": host_wdata & 0xFFFF, "zh_wdata_hi": host_wdata >> 16 & 0xFFFF}


def vectors(rng):
    out = []
    for _ in range(2000):
        r = rng.random()
        a = (0x4004_0000 + rng.randrange(0, 0x25800) if r < 0.6 else
             rng.choice([0x4006_57FC, 0x4006_5800, 0x4003_FFFC, 0x4004_0000, 0x4000_0000, 0x5000_0000]) if r < 0.75 else rng.getrandbits(32))
        out.append({"host_en": 1 if rng.random() < 0.85 else 0, "host_we": 1 if rng.random() < 0.8 else 0,
                    "host_addr": a, "host_wdata": rng.getrandbits(32)})
    return out
