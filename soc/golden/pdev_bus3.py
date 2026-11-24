"""Golden model of `pdev_bus3`: device decode and read mux of the 64 KB peripheral window with the keyboard and mouse ports. Combinational. Written by hand."""
M32 = 0xFFFFFFFF
NAMES = {0: "gpio", 1: "spi", 2: "i2c", 3: "kbd", 4: "mouse"}


def golden_pdev_bus3(pa, pw, pr, gpio_rdata, spi_rdata, i2c_rdata, kbd_rdata, mouse_rdata):
    rd = {"gpio": gpio_rdata, "spi": spi_rdata, "i2c": i2c_rdata, "kbd": kbd_rdata, "mouse": mouse_rdata}
    dev = NAMES.get(pa >> 8 & 15)
    out = {f"{n}_we": int(bool(pw & 1) and dev == n) for n in ("gpio", "spi", "i2c", "kbd", "mouse")}
    out["kbd_re"] = int(bool(pr & 1) and dev == "kbd")
    out["mouse_re"] = int(bool(pr & 1) and dev == "mouse")
    out["prdata"] = rd[dev] & M32 if dev else 0
    return out


def vectors(rng):
    out = []
    for _ in range(3000):
        pa = (0x10010000 | rng.getrandbits(16)) if rng.random() < 0.8 else rng.getrandbits(32)
        if rng.random() < 0.4:
            pa = (pa & ~(15 << 8)) | (rng.randrange(0, 7) << 8)
        out.append({"pa": pa, "pw": rng.getrandbits(1), "pr": rng.getrandbits(1), **{f"{n}_rdata": rng.getrandbits(32) for n in ("gpio", "spi", "i2c", "kbd", "mouse")}})
    return out
