"""Golden model of `pdev_bus2`: device decode and read mux of the peripheral window with the framebuffer, keyboard, mouse and display. Combinational. Written by hand."""
M32 = 0xFFFFFFFF
NAMES = {0: "gpio", 1: "spi", 2: "i2c", 3: "kbd", 4: "mouse", 5: "disp"}


def golden_pdev_bus2(pa, pw, gpio_rdata, spi_rdata, i2c_rdata, kbd_rdata, mouse_rdata, disp_rdata, fb_rdata):
    rd = {"gpio": gpio_rdata, "spi": spi_rdata, "i2c": i2c_rdata, "kbd": kbd_rdata, "mouse": mouse_rdata, "disp": disp_rdata, "fb": fb_rdata}
    dev = "fb" if (pa >> 18 & 3) == 1 else NAMES.get(pa >> 8 & 15)
    out = {f"{n}_we": int(bool(pw & 1) and dev == n) for n in ("gpio", "spi", "i2c", "kbd", "mouse", "disp", "fb")}
    out["prdata"] = rd[dev] & M32 if dev else 0
    return out


def vectors(rng):
    out = []
    for _ in range(4000):
        pa = (0x10010000 | rng.getrandbits(20)) if rng.random() < 0.7 else rng.getrandbits(32)
        if rng.random() < 0.3:
            pa = (pa & ~(15 << 8)) | (rng.randrange(0, 8) << 8)
        if rng.random() < 0.2:
            pa = (pa & ~(3 << 18)) | (1 << 18)
        out.append({"pa": pa, "pw": rng.getrandbits(1), **{f"{n}_rdata": rng.getrandbits(32) for n in ("gpio", "spi", "i2c", "kbd", "mouse", "disp", "fb")}})
    return out
