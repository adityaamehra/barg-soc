"""Golden model of `pdev_bus`: device decode and read mux of the peripheral window. Written by hand."""


def golden_pdev_bus(pa, pw, gpio_rdata, spi_rdata, i2c_rdata):
    d = (pa >> 8) & 0xF
    w = pw & 1
    return {"gpio_we": int(w and d == 0), "spi_we": int(w and d == 1), "i2c_we": int(w and d == 2),
            "prdata": gpio_rdata if d == 0 else spi_rdata if d == 1 else i2c_rdata if d == 2 else 0}


def vectors(rng):
    out = []
    for _ in range(2500):
        a = (rng.getrandbits(32) & ~0xF00) | (rng.choice([0, 1, 2, 3, 4, 7, 15, rng.getrandbits(4)]) << 8)
        out.append({"pa": a & 0xFFFFFFFF, "pw": rng.getrandbits(1), "gpio_rdata": rng.getrandbits(32), "spi_rdata": rng.getrandbits(32), "i2c_rdata": rng.getrandbits(32)})
    return out
