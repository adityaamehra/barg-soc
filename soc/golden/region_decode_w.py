"""Golden model of the data-side region decoder of the final SoC (quad core, GPU cluster, peripherals). Written by hand.
RAM 0x8000_0000 64 MB; CLINT 0x0200_0000 64 KB; PLIC 0x0C00_0000 64 MB; UART 0x1000_0000 4 KB; peripherals 0x1001_0000 to 0x100F_FFFF (960 KB);
GPU cluster 0x3000_0000 32 MB."""


def golden_region_decode_w(addr):
    addr &= 0xFFFFFFFF
    ram, clint = addr >> 26 == 0b100000, addr >> 16 == 0x0200
    plic, uart = addr >> 26 == 0b000011, addr >> 12 == 0x10000
    periph, gpu = (addr >> 20 == 0x100 and (addr >> 16) & 15 != 0), addr >> 25 == 0x18
    return {"sel_ram": int(ram), "sel_clint": int(clint), "sel_plic": int(plic), "sel_uart": int(uart), "sel_periph": int(periph),
            "sel_gpu": int(gpu), "is_io": int(clint or plic or uart or periph or gpu)}


def vectors(rng):
    bases = [0x8000_0000, 0x0200_0000, 0x0C00_0000, 0x1000_0000, 0x1001_0000, 0x3000_0000, 0x3100_0000, 0x2F00_0000, 0x3200_0000,
             0x1002_0000, 0x1000_F000, 0x100F_FFFC, 0x1010_0000, 0x1004_0000, 0x1008_0000, 0x83FF_FFFC, 0x8400_0000, 0x31FF_FFFC, 0x7FFF_FFFC]
    out = [{"addr": b + o} for b in bases for o in (0, 4, 0xFFC, 0xFFFC)]
    for _ in range(3000):
        out.append({"addr": (rng.choice(bases) + (rng.getrandbits(24) if rng.random() < 0.5 else rng.getrandbits(12))) & 0xFFFFFFFF
                    if rng.random() < 0.7 else rng.getrandbits(32)})
    return out
