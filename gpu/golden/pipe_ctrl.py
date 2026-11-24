"""Golden model of the pipeline control (block `pipe_ctrl`). Combinational.

The X stage is busy while it holds a division whose result is not ready, or a memory access the load-store unit has not
finished: x_busy = dx_valid & ((unit == DIV(2) & !div_ready) | (unit == LSU(3) & !lsu_ready)).
stall = x_busy (the S, D and X stages hold). advance = dx_valid & !x_busy: the X-stage instruction completes at the next
edge. sched_en = running & !stall. fetch_idx = bits 10:2 of (sf_pc when stall is 1, else sel_pc): the instruction memory
word to read, so that a held D stage keeps seeing its own instruction.
"""


def golden_pipe_ctrl(running, dx_valid, unit, div_ready, lsu_ready, sel_pc, sf_pc):
    busy = bool(dx_valid & 1) and ((unit == 2 and not div_ready & 1) or (unit == 3 and not lsu_ready & 1))
    return {"stall": int(busy), "advance": int(bool(dx_valid & 1) and not busy),
            "sched_en": int(bool(running & 1) and not busy), "fetch_idx": ((sf_pc if busy else sel_pc) >> 2) & 511}
