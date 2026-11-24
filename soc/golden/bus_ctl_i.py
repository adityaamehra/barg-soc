"""Golden model of `bus_ctl_i`: the data-side strobes of the final SoC, device strobes only while the memory engine is idle. Written by hand."""

SELS = ("sel_ram", "sel_clint", "sel_plic", "sel_uart", "sel_periph", "sel_gpu")


def golden_bus_ctl_i(memwrite, memsrc, valid, xcpt, kill, sel_ram, sel_clint, sel_plic, sel_uart, sel_periph, sel_gpu, idle):
    write = memwrite & 1
    ok = (memsrc & 3) == 1 and (valid & 1) and not (xcpt & 1) and not (kill & 1)
    w = lambda s: int(bool(write and s & 1))  # noqa: E731
    r = lambda s: int(bool(ok and s & 1 and idle & 1))  # noqa: E731
    wd = lambda s: int(bool(write and s & 1 and idle & 1))  # noqa: E731
    return {"ram_we": w(sel_ram), "clint_we": wd(sel_clint), "plic_we": wd(sel_plic), "uart_we": wd(sel_uart), "periph_we": wd(sel_periph),
            "gpu_we": wd(sel_gpu), "plic_re": r(sel_plic), "uart_re": r(sel_uart), "periph_re": r(sel_periph), "gpu_re": r(sel_gpu)}


def vectors(rng):
    out = []
    for _ in range(4000):
        sel = rng.choice(SELS + (None,))
        out.append({"memwrite": rng.randrange(2), "memsrc": 1 if rng.random() < 0.6 else rng.randrange(4),
                    "valid": 1 if rng.random() < 0.8 else 0, "xcpt": 1 if rng.random() < 0.15 else 0, "kill": 1 if rng.random() < 0.15 else 0,
                    "idle": 1 if rng.random() < 0.6 else 0, **{s: int(s == sel) for s in SELS}})
    return out
