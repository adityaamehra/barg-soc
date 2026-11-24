"""Graphics kernels for the SIMT GPU, hand-assembled (no compiler), each with an independent Python model of the frame it draws.

    kernel_g1b(rows)   machine code of the stage-G1b kernel;  frame_g1b(rows)  the 320 x 240 RGB565 frame it must produce.

G1b kernel, 4 warps of 4 lanes (warp w draws rows w, w + 4, ...; lane l the pixel x0 + l of a group of four):
  P1  fill rows 0 .. rows-1 with one colour;                                       (barrier)
  P2  set the scissor box (gfx.cfg), then draw a gradient over the whole of rows 0 .. rows-1 (the box clips it);   (barrier)
  P3  warp 0 only, a few pixel writes that test the rules of `pix`: pixels outside the box, a restored box, four lanes on
      one bank (the highest lane wins), pixels off the screen, two lanes switched off, and gfx.cfg called with a lane mask
      (the lowest active lane's operands are used).
The frame model below is written from the rules in ISA/gfx-architecture only: it does not use model/simt.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "model"))
from asm import Asm  # noqa: E402

W, H = 320, 240
FILL = 0xFF102030
BOX = (16, 8, 300)           # scissor x0, y0, x1; y1 = rows - 8


def rgb565(argb: int) -> int:
    return (argb >> 19 & 31) << 11 | (argb >> 10 & 63) << 5 | (argb >> 3 & 31)


def gradient(x: int, y: int) -> int:
    return 0xFF000000 | ((x * 51) >> 6) << 16 | ((y * 17) >> 4) << 8 | (x + y) & 255


def kernel_g1b(rows: int = H) -> bytes:
    a = Asm()
    a.li("t0", 4)
    a.la("t1", "body")
    a.wspawn("t0", "t1")
    a.label("body")
    a.li("t0", 0xF)
    a.tmc("t0")
    a.csrr("s0", "wid")
    a.csrr("s1", "tid")

    def pass_over_rows(name, colour):
        """for y = wid; y < rows; y += 4: for x0 = 0; x0 < 320; x0 += 4: pix((y << 16) | (x0 + tid), colour(x0 + tid, y))"""
        a.mv("s2", "s0")                                   # y
        a.label(f"{name}_row")
        a.li("t0", rows)
        a.bge("s2", "t0", f"{name}_done")
        a.slli("s4", "s2", 16)                             # y << 16
        a.mv("s3", "s1")                                   # x = x0 + tid, from tid
        a.label(f"{name}_col")
        a.or_("s5", "s4", "s3")                            # pixel position
        colour()
        a.pix("s5", "s6")
        a.addi("s3", "s3", 4)
        a.li("t0", W)
        a.blt("s3", "t0", f"{name}_col")
        a.addi("s2", "s2", 4)
        a.j(f"{name}_row")
        a.label(f"{name}_done")

    def cfg(reg, value):
        a.li("t0", reg)
        a.li("t1", value)
        a.gfx_cfg("t0", "t1")

    pass_over_rows("fill", lambda: a.li("s6", FILL))
    a.li("t0", 0)
    a.li("t1", 4)
    a.bar("t0", "t1")
    cfg(0, BOX[0]), cfg(1, BOX[1]), cfg(2, BOX[2]), cfg(3, rows - 8)

    def grad():                                            # s3 = x, s2 = y
        a.li("t0", 51), a.mul("t1", "s3", "t0"), a.srli("t1", "t1", 6), a.slli("t1", "t1", 16)      # r << 16
        a.li("t0", 17), a.mul("t2", "s2", "t0"), a.srli("t2", "t2", 4), a.slli("t2", "t2", 8)       # g << 8
        a.add("t3", "s3", "s2"), a.andi("t3", "t3", 255)                                              # b
        a.or_("t1", "t1", "t2"), a.or_("t1", "t1", "t3")
        a.lui("t0", 0xFF000), a.or_("s6", "t1", "t0")                                                 # alpha

    pass_over_rows("grad", grad)
    a.li("t0", 1)
    a.li("t1", 4)
    a.bar("t0", "t1")
    a.bnez("s0", "end")                                    # P3: warp 0 only (the branch is the same in all lanes)
    r0 = rows - 20

    def pix_at(y, x_expr, colour):                         # x_expr(): leaves x in t2 from tid in s1
        a.li("t0", y << 16)
        x_expr()
        a.or_("t0", "t0", "t2")
        colour()
        a.pix("t0", "t1")

    # S1: row 0 is above the box's y0: dropped
    pix_at(0, lambda: a.mv("t2", "s1"), lambda: a.li("t1", 0xFFFF0000))
    # restore the box
    cfg(0, 0), cfg(1, 0), cfg(2, W), cfg(3, H)
    # S2: four lanes on bank 0 (x = 0, 4, 8, 12): the highest lane wins; colour 0xFF000000 | (lane + 1) << 19
    pix_at(r0, lambda: a.slli("t2", "s1", 2), lambda: (a.addi("t1", "s1", 1), a.slli("t1", "t1", 19), a.lui("t3", 0xFF000), a.or_("t1", "t1", "t3")))
    # S3: x = 316, 318, 320, 322: the last two are off the screen; and y = 240 for all lanes
    pix_at(r0 + 1, lambda: (a.slli("t2", "s1", 1), a.addi("t2", "t2", 316)), lambda: a.li("t1", 0xFFFFFFFF))
    a.li("t0", 240 << 16)
    a.or_("t0", "t0", "s1")
    a.li("t1", 0xFF00FF00)
    a.pix("t0", "t1")
    a.li("t0", 0xFFFF0000)
    a.or_("t0", "t0", "s1")
    a.pix("t0", "t1")
    # S4: lanes 0 and 2 only
    a.li("t0", 5)
    a.tmc("t0")
    pix_at(r0 + 2, lambda: a.mv("t2", "s1"), lambda: a.li("t1", 0xFF00FF00))
    a.li("t0", 0xF)
    a.tmc("t0")
    # S5: gfx.cfg from lanes 2 and 3 only: the lowest active lane (2) gives register 2 and value 202 (lane 3 would give 3, 203)
    a.li("t0", 12)
    a.tmc("t0")
    a.addi("t1", "s1", 200)                                # value 200 + tid
    a.gfx_cfg("s1", "t1")                                  # register tid = 2, value 202: the box's x1
    a.li("t0", 0xF)
    a.tmc("t0")
    pix_at(r0 + 3, lambda: a.addi("t2", "s1", 200), lambda: a.li("t1", 0xFF123456))     # x = 200 .. 203: 202, 203 are outside
    a.label("end")
    a.tmc("zero")
    return a.assemble()


def frame_g1b(rows: int = H) -> list[int]:
    """The frame, as a list of 320 * 240 RGB565 values (pixels never drawn are 0)."""
    f = [0] * (W * H)
    for y in range(rows):
        for x in range(W):
            f[y * W + x] = rgb565(FILL)
    x0, y0, x1, y1 = BOX[0], BOX[1], BOX[2], rows - 8
    for y in range(rows):
        for x in range(W):
            if x0 <= x < x1 and y0 <= y < y1:
                f[y * W + x] = rgb565(gradient(x, y))
    r0 = rows - 20
    # S1: y = 0 is above y0: nothing. S2: x = 4 * lane, all bank 0: lane 3's colour at x = 12
    f[r0 * W + 12] = rgb565(0xFF000000 | (3 + 1) << 19)
    # S3: x = 316 and 318 on row r0 + 1; x = 320, 322 and the y = 240 rows are off the screen
    f[(r0 + 1) * W + 316] = f[(r0 + 1) * W + 318] = rgb565(0xFFFFFFFF)
    # S4: lanes 0 and 2
    f[(r0 + 2) * W + 0] = f[(r0 + 2) * W + 2] = rgb565(0xFF00FF00)
    # S5: x1 = 202: pixels 200 and 201 of row r0 + 3
    f[(r0 + 3) * W + 200] = f[(r0 + 3) * W + 201] = rgb565(0xFF123456)
    return f
