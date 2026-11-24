"""Golden model of the pipeline control of `simt-gpu-gfx` (block `pipe_ctrl`). Combinational. Never shown to the generator.

As the GPU core's (../golden/pipe_ctrl.py) plus one input, g_busy (the graphics units need another cycle: tex, G2c):
x_busy = (dx_valid & ((unit == DIV(2) & !div_ready) | (unit == LSU(3) & !lsu_ready))) | g_busy.
stall = x_busy. advance = dx_valid & !x_busy. sched_en = running & !x_busy. fetch_idx = bits 10:2 of (sf_pc when x_busy is 1, else
sel_pc).
"""


def golden_pipe_ctrl(running, dx_valid, unit, div_ready, lsu_ready, sel_pc, sf_pc, g_busy):
    busy = (bool(dx_valid & 1) and ((unit == 2 and not div_ready & 1) or (unit == 3 and not lsu_ready & 1))) or bool(g_busy & 1)
    return {"stall": int(busy), "advance": int(bool(dx_valid & 1) and not busy),
            "sched_en": int(bool(running & 1) and not busy), "fetch_idx": ((sf_pc if busy else sel_pc) >> 2) & 511}


def vectors(rng):
    out = []
    for _ in range(1500):
        out.append({"running": rng.randrange(2), "dx_valid": 1 if rng.random() < 0.8 else 0, "unit": rng.randrange(8),
                    "div_ready": rng.randrange(2), "lsu_ready": rng.randrange(2), "sel_pc": rng.getrandbits(32),
                    "sf_pc": rng.getrandbits(32), "g_busy": 1 if rng.random() < 0.3 else 0})
    return out
