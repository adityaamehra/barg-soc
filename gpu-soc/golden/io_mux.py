"""A golden model of the device read-data multiplexer of the GPU SoC. Written by hand."""


def golden_io_mux(clint_rdata, plic_rdata, uart_rdata, gpu_rdata, sel_clint, sel_plic, sel_uart, sel_gpu):
    y = (clint_rdata if sel_clint & 1 else plic_rdata if sel_plic & 1 else uart_rdata if sel_uart & 1 else
         gpu_rdata if sel_gpu & 1 else 0)
    return {"y": y & 0xFFFFFFFF}


def vectors(rng):
    out = []
    for _ in range(2000):
        sel = rng.choice(["sel_clint", "sel_plic", "sel_uart", "sel_gpu", None])
        out.append({**{k: rng.getrandbits(32) for k in ("clint_rdata", "plic_rdata", "uart_rdata", "gpu_rdata")},
                    **{s: int(s == sel) for s in ("sel_clint", "sel_plic", "sel_uart", "sel_gpu")}})
    return out
