"""A golden model of the data-side region decoder of the GPU SoC: the stage-4 map plus the GPU window. Written by hand."""


def golden_region_decode(addr):
    addr &= 0xFFFFFFFF
    ram, clint = addr >> 24 == 0x80, addr >> 16 == 0x0200
    plic, uart = addr >> 26 == 0b000011, addr >> 12 == 0x10000
    gpu = addr >> 24 == 0x30
    return {"sel_ram": int(ram), "sel_clint": int(clint), "sel_plic": int(plic), "sel_uart": int(uart), "sel_gpu": int(gpu),
            "is_io": int(clint or plic or uart or gpu)}


def vectors(rng):
    out = []
    for _ in range(3000):
        r = rng.random()
        a = (rng.choice([0x8000_0000, 0x0200_0000, 0x0C00_0000, 0x1000_0000, 0x3000_0000, 0x2F00_0000, 0x3100_0000, 0x30FF_FFFC])
             + (rng.getrandbits(24) if rng.random() < 0.5 else rng.getrandbits(12))) if r < 0.7 else rng.getrandbits(32)
        out.append({"addr": a & 0xFFFFFFFF})
    return out
