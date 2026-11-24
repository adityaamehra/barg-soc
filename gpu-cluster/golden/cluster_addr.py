"""Golden model of the address splitter of the GPU cluster (block `cluster_addr`). Combinational. Written by hand."""


def golden_cluster_addr(addr):
    addr &= 0xFFFFFFFF
    return {"local_addr": addr & ~(0xF << 21) & 0xFFFFFFFF, "slot": (addr >> 21) & 0xF}


def vectors(rng):
    out = [{"addr": a} for a in (0, 0xFFFFFFFF, 0x3000_0000, 0x3020_0000, 0x31E0_0000, 0x31FF_FFFC, 0x3010_0000)]
    for _ in range(2000):
        out.append({"addr": 0x3000_0000 | rng.getrandbits(25) if rng.random() < 0.8 else rng.getrandbits(32)})
    return out
