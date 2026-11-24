"""A golden model of the strobes of the data-side regions of the GPU SoC: the stage-4 ones plus the GPU's. Written by hand."""


def golden_bus_ctl(memwrite, memsrc, valid, xcpt, kill, sel_ram, sel_clint, sel_plic, sel_uart, sel_gpu):
    write = memwrite & 1
    ok = (memsrc & 3) == 1 and (valid & 1) and not (xcpt & 1) and not (kill & 1)
    return {"ram_we": int(bool(write and sel_ram & 1)), "clint_we": int(bool(write and sel_clint & 1)),
            "plic_we": int(bool(write and sel_plic & 1)), "uart_we": int(bool(write and sel_uart & 1)),
            "gpu_we": int(bool(write and sel_gpu & 1)),
            "plic_re": int(bool(ok and sel_plic & 1)), "uart_re": int(bool(ok and sel_uart & 1)), "gpu_re": int(bool(ok and sel_gpu & 1))}


def vectors(rng):
    out = []
    for _ in range(2000):
        sel = rng.choice(["sel_ram", "sel_clint", "sel_plic", "sel_uart", "sel_gpu", None])
        out.append({"memwrite": rng.randrange(2), "memsrc": 1 if rng.random() < 0.6 else rng.randrange(4),
                    "valid": 1 if rng.random() < 0.8 else 0, "xcpt": 1 if rng.random() < 0.15 else 0, "kill": 1 if rng.random() < 0.15 else 0,
                    **{s: int(s == sel) for s in ("sel_ram", "sel_clint", "sel_plic", "sel_uart", "sel_gpu")}})
    return out
