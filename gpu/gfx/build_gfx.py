"""Graphics stages G1a and G1b of the SIMT GPU (`simt-gpu-gfx`): video memory, a display controller, the host window onto them, and the
first graphics instructions (gfx.cfg and pix).

    python3 demos/simt-gpu/gfx/build_gfx.py        # writes gfx/design.json

The design is the GPU core of ../build.py (its 36 blocks and nets, unchanged) plus:
  vwbank0..3, vdbank0..3  video memory, 320 x 240 pixels of 16 bits (RGB565). Pixel p = y*320 + x is in bank p mod 4 at index
                          p / 4. Two copies written identically: the work copy (vw) is read by the host (later by the ROP), the
                          display copy (vd) only by the display controller, so neither ever waits for the other.
  gfx_host                the host bus side: the video memory window at 0x4000_0000, DISP_CTRL / DISP_STATUS at 0x3000_0020/24,
                          and the read-data select between the core's host_if and these.
  disp_ctrl               VGA 640 x 480 at 60 Hz timing (800 x 525 clocks a frame) showing the 320 x 240 image doubled.
G1b adds the instructions gfx.cfg and pix (opcode custom-2, 0x5B): `decode` and `dx_reg` are regenerated (new fields gfx and gfx_op; a
graphics instruction has unit NONE, so no other unit reacts), and new blocks `gfx_regs` (the scissor box), `rop_unit` (the pixel write,
one video-memory write per bank) and `vram_mux` (the ROP owns the video-memory write ports while the core runs, the host otherwise).
Edit this file, not the JSON.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
import build as gpu  # noqa: E402

i, o, clocked, block, port, W, b = gpu.i, gpu.o, gpu.clocked, gpu.block, gpu.port, gpu.W, gpu.b
frm, to = gpu.frm, gpu.to

SCREEN_W, SCREEN_H = 320, 240
DEPTH = SCREEN_W * SCREEN_H // 4          # 19200 words per bank
ABITS = 15                                # bank index width
VRAM_BASE, VRAM_BYTES = 0x4000_0000, SCREEN_W * SCREEN_H * 2   # 0x4000_0000 .. 0x4002_57FF


def vbank(name, what):
    return block(f"b_{name}", name, f"{what}: {DEPTH} words of 16 bits, one write port and one read port.", [
        port("p_clk", "clk", "in", 1, "clock"), i("we", 1, "control"), i("waddr", ABITS, "addr"), i("wdata", 16, "data"),
        i("raddr", ABITS, "addr"), o("rdata", 16, "data"),
    ], latency=1, storage={
        # rdata shows the word raddr selected at the last rising edge, as it was before that edge's write; all zeros at power-up
        "kind": "memory", "depth": DEPTH, "readStyle": "sync", "sameCycle": "old", "initial": "zeros",
        "resetClears": False, "zeroReg": False,
        "ports": {"we": "p_we", "wdata": "p_wdata", "rdata": "p_rdata", "waddr": "p_waddr", "raddr": "p_raddr"},
    })


VWBANKS = [vbank(f"vwbank{k}", f"Video memory, work copy, bank {k} (pixels p with p mod 4 = {k}, at index p / 4)") for k in range(4)]
VDBANKS = [vbank(f"vdbank{k}", f"Video memory, display copy, bank {k} (pixels p with p mod 4 = {k}, at index p / 4)")
           for k in range(4)]

GFX_HOST = block("b_gfx_host", "gfx_host", """
    Host-bus side of the graphics hardware. The host bus: host_en, host_we, host_addr (32), host_wdata (32) in; a read's data is
    shown on host_rdata in the cycle after the request. core_rdata is the GPU core's own read data for that same request (it
    already follows the one-cycle rule), shown unchanged for every address this block does not own.
    Registers, all 0 after reset: raddr (32 bits, the address of the last host request) and disp_en (1 bit).
    The video memory window: host_addr is in it when host_addr bits 31:18 equal 14'h1000 (0x4000_0000 .. 0x4003_FFFF),
    host_addr bits 17:0 are less than 18'h25800, and host_addr bits 1:0 are 00. Such a word holds two pixels:
    its low half (bits 15:0) is pixel p = host_addr bits 17:1 (an even number) and its high half (bits 31:16) is pixel p + 1.
    Pixel p is in bank p mod 4 at index p / 4, so the word goes to banks 0 (low half) and 1 (high half) when host_addr bit 2 is 0,
    and to banks 2 (low half) and 3 (high half) when host_addr bit 2 is 1, at index host_addr bits 17:3 in both.
    Combinational outputs: v_waddr = host_addr bits 17:3 (15 bits); vw_raddr = host_addr bits 17:3 (15 bits);
    v_wdata_lo = host_wdata bits 15:0; v_wdata_hi = host_wdata bits 31:16; with wr = host_en & host_we & (host_addr is in the
    video memory window): v_we0 = wr & !host_addr bit 2; v_we1 = wr & !host_addr bit 2; v_we2 = wr & host_addr bit 2;
    v_we3 = wr & host_addr bit 2. disp_en shows its register.
    host_rdata, combinational from the register raddr: when raddr is in the video memory window (the same three tests applied to
    raddr), {vw_rdata1, vw_rdata0} when raddr bit 2 is 0, {vw_rdata3, vw_rdata2} when raddr bit 2 is 1 (the first named is
    bits 31:16); when raddr is 32'h3000_0020 (DISP_CTRL), {31'b0, disp_en}; when raddr is 32'h3000_0024 (DISP_STATUS),
    {16'b0, frame (8 bits), 7'b0, vblank}; anywhere else core_rdata.
    On each rising edge: when rst is 1 raddr = 0 and disp_en = 0. Otherwise raddr = host_addr (on every edge, whether or not
    host_en is 1), and when host_en & host_we & (host_addr == 32'h3000_0020), disp_en = host_wdata bit 0.
    Example: a write of 32'hF800_001F to 0x4000_0004 sets v_we2 = v_we3 = 1, v_waddr = 0, v_wdata_lo = 16'h001F (pixel 2, in
    bank 2) and v_wdata_hi = 16'hF800 (pixel 3, in bank 3). A read of 0x4000_0004 in one cycle, with vw_rdata2 = 16'h001F and
    vw_rdata3 = 16'hF800 in the next, shows host_rdata = 32'hF800_001F in that next cycle.
""", gpu.clocked(i("host_en", 1, "valid"), i("host_we", 1, "control"), i("host_addr", W, "addr"), i("host_wdata", W, "data"),
                 i("core_rdata", W, "data"), *[i(f"vw_rdata{k}", 16, "data") for k in range(4)], i("vblank", 1, "control"),
                 i("frame", 8, "data"),
                 *[o(f"v_we{k}", 1, "control") for k in range(4)], o("v_waddr", ABITS, "addr"), o("v_wdata_lo", 16, "data"),
                 o("v_wdata_hi", 16, "data"), o("vw_raddr", ABITS, "addr"), o("host_rdata", W, "data"),
                 o("disp_en", 1, "control")), reset_style="sync", latency=1)

DISP_CTRL = block("b_disp_ctrl", "disp_ctrl", """
    Display controller: VGA 640 x 480 at 60 Hz timing, one pixel per clock, showing a 320 x 240 image with every pixel doubled
    in both directions. A line is 800 clocks (640 visible, then 16 front porch, 96 sync, 48 back porch); a frame is 525 lines
    (480 visible, then 10 front porch, 2 sync, 33 back porch). The image is read from four memory banks: image pixel p = y*320 + x
    is in bank p mod 4 at index p / 4; all four banks get the same address vd_raddr, and bank k's word shows on vd_rdata<k> in
    the cycle after the address (a synchronous read).
    Registers, all 0 after reset: hc (10 bits, the column), vc (10 bits, the line), frame (8 bits), d_hc (10), d_vc (10),
    d_on (1); d_hc, d_vc and d_on are hc, vc and "enabled" delayed by one clock, so they describe the pixel whose data is
    arriving on vd_rdata now.
    On each rising edge: when rst is 1 every register becomes 0. Otherwise, when enable is 0: hc = 0, vc = 0, d_on = 0 (frame,
    d_hc and d_vc keep their values). Otherwise (enable is 1): d_hc = hc, d_vc = vc, d_on = 1, and the counters step: when hc is
    799, hc = 0 and (when vc is 524, vc = 0 and frame = frame + 1, wrapping at 256; otherwise vc = vc + 1); otherwise
    hc = hc + 1.
    Combinational outputs: vd_raddr (15 bits) = (vc >> 1) * 80 + (hc >> 3) when hc < 640 and vc < 480, else 0 (each read
    brings the four image pixels (hc >> 1) & ~3 .. +3 of image line vc >> 1, one per bank). vblank = (vc >= 480).
    frame shows its register. With vis = d_on & (d_hc < 640) & (d_vc < 480): de = vis; rgb (16 bits) = vd_rdata<k> with
    k = (d_hc >> 1) & 3 when vis, else 0; hsync = 0 when d_on & (656 <= d_hc < 752), else 1; vsync = 0 when
    d_on & (490 <= d_vc < 492), else 1 (both syncs are active low).
    Example: after reset with enable held at 1, at the first edge d_on = 1, d_hc = 0, d_vc = 0 and hc becomes 1; in the next
    cycle de = 1 and rgb = vd_rdata0 (image pixel 0), and vd_raddr = 0 (hc = 1).
""", gpu.clocked(i("enable", 1, "control"), *[i(f"vd_rdata{k}", 16, "data") for k in range(4)],
                 o("vd_raddr", ABITS, "addr"), o("hsync", 1, "control"), o("vsync", 1, "control"), o("de", 1, "control"),
                 o("rgb", 16, "data"), o("vblank", 1, "control"), o("frame", 8, "data")), reset_style="sync", latency=1)


# --------------------------------------------------------------------------- #
# G1b: graphics instructions
# --------------------------------------------------------------------------- #

def dx_fields():
    out = []
    for f in gpu.DX_FIELDS:
        out.append(f)
        if f[0] == "tensor_op":
            out += [("gfx", 1, "control", None), ("gfx_op", 3, "control", None)]
    return out


DX_FIELDS = dx_fields()
DX_REG = gpu.pipe_register("b_dx_reg", "dx_reg", "D/X pipeline register, between the decoder and the execution units", DX_FIELDS)

_decode = dict(gpu.DECODE)
_decode["description"] = " ".join((_decode["description"]
    .replace("tensor_op = funct3 bits 1:0, simt_mode", "tensor_op = funct3 bits 1:0, gfx_op = funct3 (bits 14:12), simt_mode")
    .replace("simt_mode = funct7 (bits 31:25) bits 1:0.", "simt_mode = instruction bits 26:25 (the two lowest bits of funct7).")
    .replace("illegal 0. The classes", "illegal 0, gfx 0. The classes")
    .replace("; f7 1: unit MUL", "; f7 0x20 with any f3 other than 0 and 5 (that is 1, 2, 3, 4, 6, 7) is illegal, as is any f7 other than 0, 0x20 and 1; f7 1: unit MUL")
    .replace("Any other instruction is illegal.", "Graphics (opcode 0x5B = 7'b1011011, custom-2), only with f7 = 0: f3 0 (gfx.cfg) or 5 (pix) is legal when rd = 0, with gfx = 1 "
             "and every other output its default (so unit is NONE and regwrite 0); f3 1 (rast), 3 (rast.edge), 4 (tex) or 6 (ztest) is "
             "legal with any rd, rs1 and rs2, with gfx = 1, regwrite = 1 and every other output its default (unit NONE, wb_src ALU); "
             "f3 2 or 7, or f7 not 0, is illegal. Any other instruction is illegal.")).split())
_decode["ports"] = [*_decode["ports"], o("gfx", 1, "control"), o("gfx_op", 3, "control")]
DECODE = _decode

LANES = gpu.LANES
GFX_REGS = block("b_gfx_regs", "gfx_regs", f"""
    Graphics state registers set by the gfx.cfg instruction. {LANES} Four 9-bit registers, the scissor box: x0 (register number 0),
    y0 (1), x1 (2), y1 (3); sc_x0, sc_y0, sc_x1, sc_y1 show them at once. On each rising edge: when rst is 1 or clear is 1,
    x0 = 0, y0 = 0, x1 = 320, y1 = 240. Otherwise, when valid & advance & gfx are 1 and gfx_op is 0 (gfx.cfg) and tmask is not 0:
    take the lowest-numbered lane l whose tmask bit is 1; the register number is the 32-bit lane l of a and the value is the
    32-bit lane l of b; when the number is 0, 1, 2 or 3 that register takes value bits 8:0, and for any other number nothing
    changes. The unit's other inputs do not matter.
""", gpu.clocked(i("clear", 1, "control"), i("valid", 1, "valid"), i("advance", 1, "control"), i("gfx", 1, "control"),
                 i("gfx_op", 3, "control"), i("tmask", 4, "control"), i("a", gpu.V, "data"), i("b", gpu.V, "data"),
                 o("sc_x0", 9, "data"), o("sc_y0", 9, "data"), o("sc_x1", 9, "data"), o("sc_y1", 9, "data")),
    reset_style="sync", latency=1)

ROP_UNIT = block("b_rop_unit", "rop_unit", f"""
    Raster-output unit: the pix instruction, combinational. {LANES} act = valid & advance & gfx & (gfx_op is 5). When act is 0
    every output is 0. Otherwise each lane l whose tmask bit l is 1 takes position = the 32-bit lane l of a (x = bits 15:0,
    y = bits 31:16, both unsigned) and colour = the 32-bit lane l of b (ARGB8888: alpha bits 31:24 are ignored, r = bits 23:16,
    g = bits 15:8, b = bits 7:0). The lane draws when x < 320, y < 240, sc_x0 <= x, x < sc_x1, sc_y0 <= y and y < sc_y1
    (the scissor box, 9-bit values). A drawing lane writes the video-memory bank k = x bits 1:0 at index y * 80 + (x >> 2)
    (15 bits) the 16-bit value {{r bits 7:3, g bits 7:2, b bits 7:3}}. If several drawing lanes have the same bank, the
    highest-numbered of them is the one written. For each bank k from 0 to 3: r_we<k> = 1 when some lane writes bank k, r_waddr<k>
    is its index and r_wdata<k> its value; when r_we<k> is 0, r_waddr<k> and r_wdata<k> are 0.
    Read addresses (for blending): r_raddr<k> is the index the winning lane of bank k has, found by the same rules but with
    pre = valid & gfx & (gfx_op is 5) in place of act, that is without advance (the read happens in the cycle the pipeline is
    held); r_raddr<k> is 0 when no lane draws on bank k or pre is 0.
    Blending: when blend is 1, the value written to bank k is not the plain colour but source-over: a = colour bits 31:24, the
    destination is vw_rdata<k> of the bank k being written (RGB565, the pixel now in the memory), widened to 8 bits per channel
    by repeating its top bits: with d = vw_rdata<k>, dr = {{d[15:11], d[15:13]}}, dg = {{d[10:5], d[10:9]}}, db = {{d[4:0], d[4:2]}}
    (that is r5 << 3 | r5 >> 2, g6 << 2 | g6 >> 4, b5 << 3 | b5 >> 2). For each channel, with s
    the colour's channel: x = s * a + d * (255 - a) (16 bits), and the channel is (x + 128 + ((x + 128) >> 8)) >> 8 (x / 255
    rounded). The three channels are then truncated to RGB565 as in replace mode. When blend is 0, vw_rdata<k> is not used.
""", [i("valid", 1, "valid"), i("advance", 1, "control"), i("gfx", 1, "control"), i("gfx_op", 3, "control"),
      i("tmask", 4, "control"), i("a", gpu.V, "data"), i("b", gpu.V, "data"),
      i("sc_x0", 9, "data"), i("sc_y0", 9, "data"), i("sc_x1", 9, "data"), i("sc_y1", 9, "data"),
      i("blend", 1, "control"), *[i(f"vw_rdata{k}", 16, "data") for k in range(4)],
      *[o(f"r_we{k}", 1, "control") for k in range(4)], *[o(f"r_waddr{k}", ABITS, "addr") for k in range(4)],
      *[o(f"r_wdata{k}", 16, "data") for k in range(4)], *[o(f"r_raddr{k}", ABITS, "data") for k in range(4)]])

VRAM_MUX = block("b_vram_mux", "vram_mux", """
    Video-memory write-port switch, combinational. While running is 1 the raster-output unit owns the four write ports: for bank k
    (0 to 3) m_we<k> = r_we<k>, m_waddr<k> = r_waddr<k> and m_wdata<k> = r_wdata<k>. While running is 0 the host does:
    m_we<k> = v_we<k>, m_waddr<k> = v_waddr, and m_wdata<k> = v_wdata_lo for banks 0 and 2 and v_wdata_hi for banks 1 and 3.
    The write addresses are values this switch passes through, not addresses it decodes (their port role is data).
""", [i("running", 1, "control"), *[i(f"v_we{k}", 1, "control") for k in range(4)], i("v_waddr", ABITS, "data"),
      i("v_wdata_lo", 16, "data"), i("v_wdata_hi", 16, "data"),
      *[i(f"r_we{k}", 1, "control") for k in range(4)], *[i(f"r_waddr{k}", ABITS, "data") for k in range(4)],
      *[i(f"r_wdata{k}", 16, "data") for k in range(4)],
      *[o(f"m_we{k}", 1, "control") for k in range(4)], *[o(f"m_waddr{k}", ABITS, "data") for k in range(4)],
      *[o(f"m_wdata{k}", 16, "data") for k in range(4)]])

# --------------------------------------------------------------------------- #
# G2b: the raster unit (rast, rast.edge) and the graphics write-back path
# --------------------------------------------------------------------------- #

COEFS = [f"e{k}{n}" for n in range(3) for k in "abc"]          # ea0 eb0 ec0 ea1 eb1 ec1 ea2 eb2 ec2

RASTER_REGS = block("b_raster_regs", "raster_regs", f"""
    Raster unit state, set by gfx.cfg and stepped by rast. {LANES} Registers: the box x0, y0, x1, y1 (9 bits each); nine 32-bit
    edge coefficients ea0, eb0, ec0, ea1, eb1, ec1, ea2, eb2, ec2 (gfx.cfg numbers 16 to 24 in that order); bias (3 bits, number
    25); and for each warp w from 0 to 3 a scan: sx_w and sy_w (10 bits each) and done_w (1 bit). Outputs, at once: ea0 to ec2
    and bias show their registers; s_x, s_y and s_done show the scan of the warp numbered by the input wid.
    On each rising edge: when rst is 1 or clear is 1, the box, the coefficients and bias become 0 and every warp's scan becomes
    sx = 0, sy = 0, done = 1. Otherwise a register changes only when all four hold: valid = 1, advance = 1 (when advance is 0
    the pipeline is stalled and nothing changes, whatever the other inputs), gfx = 1 and tmask is not 0. Then, with l the
    lowest-numbered lane whose tmask bit is 1:
    - gfx_op 0 (gfx.cfg): the register number n is the 32-bit lane l of a and the value v the 32-bit lane l of b. n = 8: x0 =
      v bits 8:0 with bits 1:0 cleared, y0 = v bits 24:16, and all four warps' scans restart at once. With nx = v bits 8:2
      followed by 2'b00 (the new x0), ny = v bits 24:16 and q = ny bits 1:0, for each warp w = 0, 1, 2, 3 all three of its
      scan registers are written: sx_w = nx; sy_w = ny - q + w, plus 4 when w < q (the first row at or after ny whose two
      low bits equal w); done_w = 1 when sy_w > y1 or nx > x1 (x1 and y1 as held before this edge), else 0. Example: ny = 6
      (q = 2) gives sy_0 = 8, sy_1 = 9, sy_2 = 6, sy_3 = 7. n = 9: x1 = v bits 8:0 and y1 = v bits 24:16. n = 16 to 24: that
      coefficient = v. n = 25: bias = v bits 2:0. Any other n: nothing changes. n is compared as a whole 32-bit number: a value
      such as 0x0000_0114 or 0x8000_0010 is not 20 or 16 and changes nothing.
    - gfx_op 1 (rast): only warp w = wid's scan changes, and only when done_w is 0: when sx_w + 4 > x1, then sx_w = x0, sy_w =
      sy_w + 4, and done_w = 1 when that new sy_w > y1; otherwise sx_w = sx_w + 4.
    - any other gfx_op: nothing changes.
""", gpu.clocked(i("clear", 1, "control"), i("valid", 1, "valid"), i("advance", 1, "control"), i("gfx", 1, "control"),
                 i("gfx_op", 3, "control"), i("tmask", 4, "control"), i("wid", 2, "control"), i("a", gpu.V, "data"),
                 i("b", gpu.V, "data"), *[o(c, 32, "data") for c in COEFS], o("bias", 3, "data"),
                 o("s_x", 10, "data"), o("s_y", 10, "data"), o("s_done", 1, "control")),
    reset_style="sync", latency=1)

RASTER_EVAL = block("b_raster_eval", "raster_eval", f"""
    Raster unit evaluator, combinational: the results of rast and rast.edge. {LANES} Edge function i (0, 1 or 2) at pixel (x, y):
    E_i = ea_i * x + eb_i * y + ec_i, computed in 32 bits (wrapping), with x and y unsigned. The output y has one 32-bit value
    per lane:
    - when gfx is 1, gfx_op is 1 (rast) and s_done is 1: every lane is 0xFFFFFFFF (the warp's scan is finished; this case is
      checked first and wins over the next one).
    - when gfx is 1, gfx_op is 1 (rast) and s_done is 0: lane l looks at pixel x = s_x + l, row s_y; the pixel is covered when, for each of the three edges, E_i + bias bit i, read as a signed 32-bit number, is
      greater than 0. Lane l is (s_y << 16) | x when covered and (0xFFFF << 16) | x when not (x and s_y as 16-bit fields).
    - when gfx is 1 and gfx_op is 3 (rast.edge): lane l takes the position p = the 32-bit lane l of a (x = p bits 15:0, y = p bits
      31:16) and the edge number n = bits 1:0 of the 32-bit lane l of b; the lane is E_n at (x, y), or 0 when n is 3.
    - otherwise every lane is 0.
    Example: ea0 = 0xFFFFFFF0 (-16), eb0 = 0, ec0 = 100, bias = 0: at x = 6 E_0 = 4 (covered as far as edge 0 goes), at x = 7
    E_0 = -12 (not covered).
""", [i("gfx", 1, "control"), i("gfx_op", 3, "control"), i("a", gpu.V, "data"), i("b", gpu.V, "data"),
      i("s_x", 10, "data"), i("s_y", 10, "data"), i("s_done", 1, "control"), *[i(c, 32, "data") for c in COEFS],
      i("bias", 3, "data"), o("y", gpu.V, "data")])

# --------------------------------------------------------------------------- #
# G2c-1: the texture unit (tex)
# --------------------------------------------------------------------------- #

GFX_SEL = block("b_gfx_sel", "gfx_sel", """
    Graphics write-back select, combinational: y = gfx_y | tex_y | z_y (bitwise or) when gfx is 1, otherwise y = alu_y (all
    128 bits). A graphics instruction's result (the raster unit's gfx_y, the texture unit's tex_y or the depth unit's z_y; each
    is 0 for instructions that are not its own) takes the place of the arithmetic unit's on its way to the write-back selector.
""", [i("gfx", 1, "control"), i("alu_y", gpu.V, "data"), i("gfx_y", gpu.V, "data"), i("tex_y", gpu.V, "data"),
      i("z_y", gpu.V, "data"), o("y", gpu.V, "data")])

_pipe = dict(gpu.PIPE_CTRL)
_pipe["description"] = """
    Pipeline control, combinational. The X stage is busy while it holds a division whose result is not ready, a memory access
    the load-store unit has not finished, or while the graphics units ask for another cycle (g_busy, the texture unit's
    one-cycle read): x_busy = (dx_valid & ((unit is DIV & div_ready is 0) | (unit is LSU & lsu_ready is 0))) | g_busy, with unit
    read through its encoding table. stall = x_busy (the S, D and X stages hold their instructions). advance = dx_valid &
    !x_busy: the instruction in X completes at the next rising edge. sched_en = running & !x_busy. fetch_idx = bits 10:2 of sf_pc
    when x_busy is 1, otherwise bits 10:2 of sel_pc: the instruction-memory word to read, so that a held D stage keeps seeing its
    own instruction.
"""
_pipe["ports"] = [*_pipe["ports"], i("g_busy", 1, "control")]
PIPE_CTRL = _pipe

TEX_CTRL = block("b_tex_ctrl", "tex_ctrl", f"""
    Texture unit control. {LANES} A tex instruction reads synchronous memories, so it holds the pipeline for exactly one cycle.
    Registers: pending (1 bit) and tex_mode (3 bits, the texture mode set by gfx.cfg number 32: bit 0 bilinear, bit 1 clamp u,
    bit 2 clamp v). Outputs, at once: g_busy = valid & gfx & (gfx_op is 4) & !pending; tex_mode shows its register.
    On each rising edge: when rst is 1 or clear is 1, pending = 0 and tex_mode = 0. Otherwise: pending = 0 when advance is 1;
    else pending = 1 when valid, gfx are 1 and gfx_op is 4; else pending keeps its value. And when valid, advance and gfx are
    1, gfx_op is 0 (gfx.cfg) and tmask is not 0: with l the lowest-numbered lane whose tmask bit is 1, when the 32-bit lane l
    of a equals 32 (compared as a whole 32-bit number), tex_mode = bits 2:0 of the 32-bit lane l of b.
    So a tex in X sees g_busy = 1 in its first cycle (the pipeline holds), pending becomes 1, and in the next cycle g_busy = 0,
    the instruction completes, and pending returns to 0.
""", gpu.clocked(i("clear", 1, "control"), i("valid", 1, "valid"), i("advance", 1, "control"), i("gfx", 1, "control"),
                 i("gfx_op", 3, "control"), i("tmask", 4, "control"), i("a", gpu.V, "data"), i("b", gpu.V, "data"),
                 o("g_busy", 1, "control"), o("tex_mode", 3, "control")), reset_style="sync", latency=1)

TEX_HOST = block("b_tex_host", "tex_host", """
    Texture memory host window, combinational, write only. The texture is 32 x 32 texels of 16 bits (RGB565); texel t = ty * 32
    + tx is at byte 0x5000_0000 + 2t, so a 32-bit host write at host_addr sets texels 2w (low half of host_wdata) and 2w + 1
    (high half), w = host_addr bits 10:2. Texel (tx, ty) lives in bank (ty mod 2) * 2 + (tx mod 2) at index (ty >> 1) * 16 +
    (tx >> 1). Let hit = host_en & host_we & (0x5000_0000 <= host_addr < 0x5000_0800). Then t_we0 = t_we1 = hit & (host_addr
    bit 6 is 0), t_we2 = t_we3 = hit & (host_addr bit 6 is 1); t_waddr = {host_addr bits 10:7, host_addr bits 5:2} (8 bits);
    t_wdata_lo = host_wdata bits 15:0 (for banks 0 and 2) and t_wdata_hi = host_wdata bits 31:16 (for banks 1 and 3). t_waddr
    and the data outputs follow the inputs whether or not there is a write.
""", [i("host_en", 1, "control"), i("host_we", 1, "control"), i("host_addr", W, "data"), i("host_wdata", W, "data"),
      *[o(f"t_we{k}", 1, "control") for k in range(4)], o("t_waddr", 8, "data"), o("t_wdata_lo", 16, "data"),
      o("t_wdata_hi", 16, "data")])

TEX_ADDR = block("b_tex_addr", "tex_addr", f"""
    Texture unit read addresses, combinational. {LANES} For each lane l: u = the 32-bit lane l of a and v = the 32-bit lane l of
    b, unsigned 8.8 fixed point in texels, of which only bits 15:0 count: iu = u bits 15:8, iv = v bits 15:8. Wrap of a
    coordinate c (0 to 256) on an axis: repeat (tex_mode bit 1 is 0 for u, bit 2 is 0 for v) gives c mod 32, clamp gives
    min(c, 31). x0 = wrap_u(iu), x1 = wrap_u(iu + 1), y0 = wrap_v(iv), y1 = wrap_v(iv + 1). Lane l has its own four texture
    banks; bank k = py * 2 + px holds the texels (tx, ty) with ty mod 2 = py and tx mod 2 = px, at index (ty >> 1) * 16 +
    (tx >> 1). For bank k: xk = x0 when x0 mod 2 = px, otherwise x1; yk = y0 when y0 mod 2 = py, otherwise y1; ta<l><k> = (yk
    >> 1) * 16 + (xk >> 1) (8 bits). The outputs do not depend on tex_mode bit 0 and are driven all the time.
    Example: u = 31.5 texels (0x1F80) with repeat: x0 = 31, x1 = 0; bank px = 1 reads x 31, bank px = 0 reads x 0.
""", [i("a", gpu.V, "data"), i("b", gpu.V, "data"), i("tex_mode", 3, "control"),
      *[o(f"ta{l}{k}", 8, "data") for l in range(4) for k in range(4)]])

TEX_FILTER = block("b_tex_filter", "tex_filter", f"""
    Texture unit filter, combinational: the result of tex. {LANES} When gfx is 1 and gfx_op is 4, lane l of tex_y is the
    texture sample at u = the 32-bit lane l of a, v = the 32-bit lane l of b; otherwise tex_y is 0. The texels come from lane
    l's four banks, read in the cycle before at the addresses of tex_addr (the pipeline holds the instruction for it):
    t<l><k> is bank k = py * 2 + px of lane l. iu = u bits 15:8, iv = v bits 15:8, fu = u bits 7:0, fv = v bits 7:0; x0 =
    wrap_u(iu), x1 = wrap_u(iu + 1), y0 = wrap_v(iv), y1 = wrap_v(iv + 1), where wrap is c mod 32 (repeat) or min(c, 31) (clamp)
    by tex_mode bit 1 for u and bit 2 for v. The texel at (xX, yY) is t<l><k> with k = (yY mod 2) * 2 + (xX mod 2). Each texel
    is RGB565 (r5 = bits 15:11, g6 = bits 10:5, b5 = bits 4:0), widened to 8 bits per channel: r8 = r5 << 3 | r5 >> 2, g8 =
    g6 << 2 | g6 >> 4, b8 = b5 << 3 | b5 >> 2. Point filter (tex_mode bit 0 is 0): the texel (x0, y0). Bilinear (bit 0 is 1):
    each channel is (c00 * (256 - fu) * (256 - fv) + c10 * fu * (256 - fv) + c01 * (256 - fu) * fv + c11 * fu * fv + 32768)
    >> 16, where cXY is that channel of the texel (xX, yY). The lane is 0xFF << 24 | r << 16 | g << 8 | b.
""", [i("gfx", 1, "control"), i("gfx_op", 3, "control"), i("a", gpu.V, "data"), i("b", gpu.V, "data"),
      i("tex_mode", 3, "control"), *[i(f"t{l}{k}", 16, "data") for l in range(4) for k in range(4)],
      o("tex_y", gpu.V, "data")])


def tbank(l, k):
    return block(f"b_tbank{l}{k}", f"tbank{l}{k}", f"Texture memory, lane {l}'s copy of bank {k}: 256 words of 16 bits, one write "
                 "port and one read port.", [
        port("p_clk", "clk", "in", 1, "clock"), i("we", 1, "control"), i("waddr", 8, "addr"), i("wdata", 16, "data"),
        i("raddr", 8, "addr"), o("rdata", 16, "data"),
    ], latency=1, storage={
        "kind": "memory", "depth": 256, "readStyle": "sync", "sameCycle": "old", "initial": "zeros",
        "resetClears": False, "zeroReg": False,
        "ports": {"we": "p_we", "wdata": "p_wdata", "rdata": "p_rdata", "waddr": "p_waddr", "raddr": "p_raddr"},
    })


TBANKS = [tbank(l, k) for l in range(4) for k in range(4)]

# --------------------------------------------------------------------------- #
# G2c-2: blending
# --------------------------------------------------------------------------- #

ROP_CTRL = block("b_rop_ctrl", "rop_ctrl", f"""
    Raster-output control. {LANES} Registers: blend (1 bit, set by gfx.cfg number 4: 1 source-over, 0 replace) and pending
    (1 bit). With blending on, pix reads the destination pixel in a first cycle and writes in a second, so it holds the pipeline
    one cycle. Outputs, at once: blend shows its register; g_busy = tex_busy | (valid & gfx & (gfx_op is 5) & blend & !pending)
    (the texture unit's request or this unit's, for the pipeline control).
    On each rising edge: when rst is 1 or clear is 1, blend = 0 and pending = 0. Otherwise: pending = 0 when advance is 1;
    else pending = 1 when valid and gfx are 1, gfx_op is 5 and blend is 1; else pending keeps its value. And when valid,
    advance and gfx are 1, gfx_op is 0 (gfx.cfg) and tmask is not 0: with l the lowest-numbered lane whose tmask bit is 1, when
    the 32-bit lane l of a equals 4 (compared as a whole 32-bit number), blend = bit 0 of the 32-bit lane l of b.
""", gpu.clocked(i("clear", 1, "control"), i("valid", 1, "valid"), i("advance", 1, "control"), i("gfx", 1, "control"),
                 i("gfx_op", 3, "control"), i("tmask", 4, "control"), i("a", gpu.V, "data"), i("b", gpu.V, "data"),
                 i("tex_busy", 1, "control"), o("g_busy", 1, "control"), o("blend", 1, "control")),
    reset_style="sync", latency=1)

VRAM_RMUX = block("b_vram_rmux", "vram_rmux", """
    Video-memory read-address switch for the work copy, combinational. While running is 1 the raster-output unit reads (for
    blending): m_raddr<k> = r_raddr<k> for each bank k from 0 to 3. While running is 0 the host does: every m_raddr<k> = vw_raddr.
    The addresses are values this switch passes through (their port role is data).
""", [i("running", 1, "control"), i("vw_raddr", ABITS, "data"), *[i(f"r_raddr{k}", ABITS, "data") for k in range(4)],
      *[o(f"m_raddr{k}", ABITS, "data") for k in range(4)]])

# --------------------------------------------------------------------------- #
# G2d: depth (ztest)
# --------------------------------------------------------------------------- #

Z_CTRL = block("b_z_ctrl", "z_ctrl", """
    Depth unit control. ztest reads the depth memory in a first cycle and compares and writes in a second, so it holds the
    pipeline one cycle. Register: pending (1 bit). Output, at once: g_busy = in_busy | (valid & gfx & (gfx_op is 6) & !pending),
    where in_busy is the other graphics units' request, passed on to the pipeline control. On each rising edge: when rst is 1
    or clear is 1, pending = 0; otherwise pending = 0 when advance is 1, else pending = 1 when valid and gfx are 1 and gfx_op
    is 6, else pending keeps its value.
""", gpu.clocked(i("clear", 1, "control"), i("valid", 1, "valid"), i("advance", 1, "control"), i("gfx", 1, "control"),
                 i("gfx_op", 3, "control"), i("in_busy", 1, "control"), o("g_busy", 1, "control")),
    reset_style="sync", latency=1)

Z_UNIT = block("b_z_unit", "z_unit", f"""
    Depth unit, combinational: the ztest instruction. {LANES} Every output is 0 unless gfx is 1 and gfx_op is 6. Then, for each
    lane l (0 to 3) whose tmask bit l is 1: x_l = bits 15:0 and y_l = bits 31:16 of the 32-bit lane l of a (unsigned), and the
    depth z_l = bits 15:0 of the 32-bit lane l of b. Lane l tests when x_l < 320 and y_l < 240; it then belongs to depth bank
    x_l bits 1:0 (any of the four banks, whatever l is: lanes and banks are different things) at index y_l * 80 + (x_l >> 2)
    (15 bits). For each bank k from 0 to 3, look at the lanes in the order 3, 2, 1, 0: the first lane that tests and belongs
    to bank k is bank k's winner; other lanes of bank k do not test, and bank k has no winner when no testing lane belongs to
    it. Bank k's winner, lane l, passes when z_l < z_rdata<k> (unsigned 16 bits; z_rdata<k> is bank k's stored depth, read in
    the cycle before at z_raddr<k>).
    - z_raddr<k>: when valid is 1 and bank k has a winner, the winner's index; otherwise 0.
    - Writes, when valid and advance are both 1: for each bank k whose winner passes, zw_we<k> = 1, zw_waddr<k> = the winner's
      index and zw_wdata<k> = the winner's z. For every other bank, and whenever valid or advance is 0, zw_we<k> = 0, and then
      zw_waddr<k> and zw_wdata<k> may be anything (they are used only with zw_we<k> = 1).
    - z_y: the 32-bit lane l of z_y is 0xFFFFFFFF (all ones, a lane mask) when lane l is a passing winner, else 0. It does not
      depend on valid or advance.
    Example: lane 0 at x = 6 and lane 2 at x = 10 both belong to bank 2; lane 2 is bank 2's winner and lane 0 does not test.
""", [i("valid", 1, "valid"), i("advance", 1, "control"), i("gfx", 1, "control"), i("gfx_op", 3, "control"),
      i("tmask", 4, "control"), i("a", gpu.V, "data"), i("b", gpu.V, "data"), *[i(f"z_rdata{k}", 16, "data") for k in range(4)],
      *[o(f"z_raddr{k}", ABITS, "data") for k in range(4)], *[o(f"zw_we{k}", 1, "control") for k in range(4)],
      *[o(f"zw_waddr{k}", ABITS, "data") for k in range(4)], *[o(f"zw_wdata{k}", 16, "data") for k in range(4)],
      o("z_y", gpu.V, "data")])

Z_HOST = block("b_z_host", "z_host", """
    Depth memory host window, combinational, write only. A 32-bit host write to 0x4004_0000 <= host_addr < 0x4006_5800 sets the
    depth of pixels 2w (low half of host_wdata) and 2w + 1 (high half), w = (host_addr - 0x4004_0000) >> 2; pixel p is in bank
    p mod 4 at index p >> 2. Let hit = host_en & host_we & (0x4004_0000 <= host_addr < 0x4006_5800). Then zh_we0 = zh_we1 = hit
    & (host_addr bit 2 is 0), zh_we2 = zh_we3 = hit & (host_addr bit 2 is 1); zh_waddr = host_addr bits 17:3 (15 bits);
    zh_wdata_lo = host_wdata bits 15:0 (for banks 0 and 2) and zh_wdata_hi = host_wdata bits 31:16 (for banks 1 and 3).
    zh_waddr and the data outputs follow the inputs whether or not there is a write.
""", [i("host_en", 1, "control"), i("host_we", 1, "control"), i("host_addr", W, "data"), i("host_wdata", W, "data"),
      *[o(f"zh_we{k}", 1, "control") for k in range(4)], o("zh_waddr", ABITS, "data"), o("zh_wdata_lo", 16, "data"),
      o("zh_wdata_hi", 16, "data")])

Z_MUX = block("b_z_mux", "z_mux", """
    Depth memory write-port switch, combinational. While running is 1 the depth unit owns the four write ports: for bank k (0 to
    3) mz_we<k> = zw_we<k>, mz_waddr<k> = zw_waddr<k> and mz_wdata<k> = zw_wdata<k>. While running is 0 the host does: mz_we<k>
    = zh_we<k>, mz_waddr<k> = zh_waddr, and mz_wdata<k> = zh_wdata_lo for banks 0 and 2 and zh_wdata_hi for banks 1 and 3. The
    addresses are values this switch passes through (their port role is data).
""", [i("running", 1, "control"), *[i(f"zh_we{k}", 1, "control") for k in range(4)], i("zh_waddr", ABITS, "data"),
      i("zh_wdata_lo", 16, "data"), i("zh_wdata_hi", 16, "data"),
      *[i(f"zw_we{k}", 1, "control") for k in range(4)], *[i(f"zw_waddr{k}", ABITS, "data") for k in range(4)],
      *[i(f"zw_wdata{k}", 16, "data") for k in range(4)],
      *[o(f"mz_we{k}", 1, "control") for k in range(4)], *[o(f"mz_waddr{k}", ABITS, "data") for k in range(4)],
      *[o(f"mz_wdata{k}", 16, "data") for k in range(4)]])

ZBANKS = [vbank(f"zbank{k}", f"Depth memory, bank {k} (pixels p with p mod 4 = {k}, at index p / 4)") for k in range(4)]

REGENERATED = ["decode", "dx_reg", "gfx_regs", "rop_unit", "vram_mux", "gfx_host", "disp_ctrl",
               "raster_regs", "raster_eval", "gfx_sel", "pipe_ctrl", "tex_ctrl", "tex_host", "tex_addr", "tex_filter",
               "rop_ctrl", "vram_rmux", "z_ctrl", "z_unit", "z_host", "z_mux", *[f"zbank{k}" for k in range(4)],
               *[f"tbank{l}{k}" for l in range(4) for k in range(4)]]
BLOCKS = [{"decode": DECODE, "dx_reg": DX_REG, "pipe_ctrl": PIPE_CTRL}.get(b["name"], b) for b in gpu.BLOCKS] + \
         [GFX_HOST, DISP_CTRL, GFX_REGS, ROP_UNIT, VRAM_MUX, RASTER_REGS, RASTER_EVAL, GFX_SEL, TEX_CTRL, TEX_HOST, TEX_ADDR,
          TEX_FILTER, ROP_CTRL, VRAM_RMUX, Z_CTRL, Z_UNIT, Z_HOST, Z_MUX, *VWBANKS, *VDBANKS, *TBANKS, *ZBANKS]

TOP_PORTS = [*gpu.TOP_PORTS,
             {"blockId": None, **port("t_hsync", "hsync", "out", 1, "control")},
             {"blockId": None, **port("t_vsync", "vsync", "out", 1, "control")},
             {"blockId": None, **port("t_de", "de", "out", 1, "control")},
             {"blockId": None, **port("t_rgb", "rgb", "out", 16, "data")}]


def wires():
    out = []
    add = {   # sinks added to a core net
        "clock": to("gfx_host.clk", "disp_ctrl.clk", "gfx_regs.clk", "raster_regs.clk", "tex_ctrl.clk", "rop_ctrl.clk", "z_ctrl.clk",
                    *[f"zbank{k}.clk" for k in range(4)],
                    *[f"tbank{l}{k}.clk" for l in range(4) for k in range(4)], *[f"{n}{k}.clk" for n in ("vwbank", "vdbank") for k in range(4)]),
        "reset": to("gfx_host.rst", "disp_ctrl.rst", "gfx_regs.rst", "raster_regs.rst", "tex_ctrl.rst", "rop_ctrl.rst", "z_ctrl.rst"),
        "host_en": to("gfx_host.host_en", "tex_host.host_en", "z_host.host_en"),
        "host_we": to("gfx_host.host_we", "tex_host.host_we", "z_host.host_we"),
        "host_addr": to("gfx_host.host_addr", "tex_host.host_addr", "z_host.host_addr"),
        "host_wdata": to("gfx_host.host_wdata", "tex_host.host_wdata", "z_host.host_wdata"),
        "running": to("vram_mux.running", "vram_rmux.running", "z_mux.running"),
        "start": to("gfx_regs.clear", "raster_regs.clear", "tex_ctrl.clear", "rop_ctrl.clear", "z_ctrl.clear"),
        "advance": to("gfx_regs.advance", "rop_unit.advance", "raster_regs.advance", "tex_ctrl.advance", "rop_ctrl.advance",
                      "z_ctrl.advance", "z_unit.advance"),
        "x_valid": to("gfx_regs.valid", "rop_unit.valid", "raster_regs.valid", "tex_ctrl.valid", "rop_ctrl.valid", "z_ctrl.valid",
                      "z_unit.valid"),
        "x_tmask": to("gfx_regs.tmask", "rop_unit.tmask", "raster_regs.tmask", "tex_ctrl.tmask", "rop_ctrl.tmask", "z_unit.tmask"),
        "x_a": to("gfx_regs.a", "rop_unit.a", "raster_regs.a", "raster_eval.a", "tex_ctrl.a", "tex_addr.a", "tex_filter.a",
                  "rop_ctrl.a", "z_unit.a"),
        "x_b": to("gfx_regs.b", "rop_unit.b", "raster_regs.b", "raster_eval.b", "tex_ctrl.b", "tex_addr.b", "tex_filter.b",
                  "rop_ctrl.b", "z_unit.b"),
        "x_wid": to("raster_regs.wid"),
    }
    for name, width, driver, sinks in gpu.WIRES:
        if name == "host_rdata":            # the core's read data now goes through gfx_host
            name, sinks = "core_rdata", to("gfx_host.core_rdata")
        if name == "alu_y":                 # the arithmetic result now goes through gfx_sel (G2b)
            sinks = to("gfx_sel.alu_y")
        out.append((name, width, driver, sinks + add.get(name, [])))
    out += [
        ("host_rdata", W, frm("gfx_host.host_rdata"), to("top.host_rdata")),
        *[(f"v_we{k}", 1, frm(f"gfx_host.v_we{k}"), to(f"vram_mux.v_we{k}")) for k in range(4)],
        ("v_waddr", ABITS, frm("gfx_host.v_waddr"), to("vram_mux.v_waddr")),
        ("v_wdata_lo", 16, frm("gfx_host.v_wdata_lo"), to("vram_mux.v_wdata_lo")),
        ("v_wdata_hi", 16, frm("gfx_host.v_wdata_hi"), to("vram_mux.v_wdata_hi")),
        *[(f"m_we{k}", 1, frm(f"vram_mux.m_we{k}"), to(f"vwbank{k}.we", f"vdbank{k}.we")) for k in range(4)],
        *[(f"m_waddr{k}", ABITS, frm(f"vram_mux.m_waddr{k}"), to(f"vwbank{k}.waddr", f"vdbank{k}.waddr")) for k in range(4)],
        *[(f"m_wdata{k}", 16, frm(f"vram_mux.m_wdata{k}"), to(f"vwbank{k}.wdata", f"vdbank{k}.wdata")) for k in range(4)],
        *[(f"r_we{k}", 1, frm(f"rop_unit.r_we{k}"), to(f"vram_mux.r_we{k}")) for k in range(4)],
        *[(f"r_waddr{k}", ABITS, frm(f"rop_unit.r_waddr{k}"), to(f"vram_mux.r_waddr{k}")) for k in range(4)],
        *[(f"r_wdata{k}", 16, frm(f"rop_unit.r_wdata{k}"), to(f"vram_mux.r_wdata{k}")) for k in range(4)],
        ("vw_raddr", ABITS, frm("gfx_host.vw_raddr"), to("vram_rmux.vw_raddr")),
        *[(f"vw_rdata{k}", 16, frm(f"vwbank{k}.rdata"), to(f"gfx_host.vw_rdata{k}", f"rop_unit.vw_rdata{k}")) for k in range(4)],
        ("disp_en", 1, frm("gfx_host.disp_en"), to("disp_ctrl.enable")),
        ("vd_raddr", ABITS, frm("disp_ctrl.vd_raddr"), to(*[f"vdbank{k}.raddr" for k in range(4)])),
        *[(f"vd_rdata{k}", 16, frm(f"vdbank{k}.rdata"), to(f"disp_ctrl.vd_rdata{k}")) for k in range(4)],
        ("vblank", 1, frm("disp_ctrl.vblank"), to("gfx_host.vblank")),
        ("frame", 8, frm("disp_ctrl.frame"), to("gfx_host.frame")),
        *[(f"disp_{p}", w, frm(f"disp_ctrl.{p}"), to(f"top.{p}")) for p, w in (("hsync", 1), ("vsync", 1), ("de", 1), ("rgb", 16))],
        # G1b
        ("d_gfx", 1, frm("decode.gfx"), to("dx_reg.gfx_in")),
        ("d_gfx_op", 3, frm("decode.gfx_op"), to("dx_reg.gfx_op_in")),
        ("x_gfx", 1, frm("dx_reg.gfx_out"), to("gfx_regs.gfx", "rop_unit.gfx", "raster_regs.gfx", "raster_eval.gfx", "gfx_sel.gfx",
                                                 "tex_ctrl.gfx", "tex_filter.gfx", "rop_ctrl.gfx", "z_ctrl.gfx", "z_unit.gfx")),
        ("x_gfx_op", 3, frm("dx_reg.gfx_op_out"), to("gfx_regs.gfx_op", "rop_unit.gfx_op", "raster_regs.gfx_op", "raster_eval.gfx_op",
                                                       "tex_ctrl.gfx_op", "tex_filter.gfx_op", "rop_ctrl.gfx_op", "z_ctrl.gfx_op",
                                                       "z_unit.gfx_op")),
        *[(f"sc_{p}", 9, frm(f"gfx_regs.sc_{p}"), to(f"rop_unit.sc_{p}")) for p in ("x0", "y0", "x1", "y1")],
        # G2b
        *[(f"r_{c}", 32, frm(f"raster_regs.{c}"), to(f"raster_eval.{c}")) for c in COEFS],
        ("r_bias", 3, frm("raster_regs.bias"), to("raster_eval.bias")),
        ("r_s_x", 10, frm("raster_regs.s_x"), to("raster_eval.s_x")),
        ("r_s_y", 10, frm("raster_regs.s_y"), to("raster_eval.s_y")),
        ("r_s_done", 1, frm("raster_regs.s_done"), to("raster_eval.s_done")),
        ("gfx_y", gpu.V, frm("raster_eval.y"), to("gfx_sel.gfx_y")),
        ("wb_alu_y", gpu.V, frm("gfx_sel.y"), to("wb_mux.alu_y")),
        # G2c-1
        ("tex_busy", 1, frm("tex_ctrl.g_busy"), to("rop_ctrl.tex_busy")),
        ("rop_busy", 1, frm("rop_ctrl.g_busy"), to("z_ctrl.in_busy")),
        ("g_busy", 1, frm("z_ctrl.g_busy"), to("pipe_ctrl.g_busy")),
        ("tex_mode", 3, frm("tex_ctrl.tex_mode"), to("tex_addr.tex_mode", "tex_filter.tex_mode")),
        *[(f"t_we{k}", 1, frm(f"tex_host.t_we{k}"), to(*[f"tbank{l}{k}.we" for l in range(4)])) for k in range(4)],
        ("t_waddr", 8, frm("tex_host.t_waddr"), to(*[f"tbank{l}{k}.waddr" for l in range(4) for k in range(4)])),
        ("t_wdata_lo", 16, frm("tex_host.t_wdata_lo"), to(*[f"tbank{l}{k}.wdata" for l in range(4) for k in (0, 2)])),
        ("t_wdata_hi", 16, frm("tex_host.t_wdata_hi"), to(*[f"tbank{l}{k}.wdata" for l in range(4) for k in (1, 3)])),
        *[(f"ta{l}{k}", 8, frm(f"tex_addr.ta{l}{k}"), to(f"tbank{l}{k}.raddr")) for l in range(4) for k in range(4)],
        *[(f"t{l}{k}", 16, frm(f"tbank{l}{k}.rdata"), to(f"tex_filter.t{l}{k}")) for l in range(4) for k in range(4)],
        ("tex_y", gpu.V, frm("tex_filter.tex_y"), to("gfx_sel.tex_y")),
        # G2c-2
        ("blend", 1, frm("rop_ctrl.blend"), to("rop_unit.blend")),
        *[(f"r_raddr{k}", ABITS, frm(f"rop_unit.r_raddr{k}"), to(f"vram_rmux.r_raddr{k}")) for k in range(4)],
        *[(f"m_raddr{k}", ABITS, frm(f"vram_rmux.m_raddr{k}"), to(f"vwbank{k}.raddr")) for k in range(4)],
        # G2d
        *[(f"zh_we{k}", 1, frm(f"z_host.zh_we{k}"), to(f"z_mux.zh_we{k}")) for k in range(4)],
        ("zh_waddr", ABITS, frm("z_host.zh_waddr"), to("z_mux.zh_waddr")),
        ("zh_wdata_lo", 16, frm("z_host.zh_wdata_lo"), to("z_mux.zh_wdata_lo")),
        ("zh_wdata_hi", 16, frm("z_host.zh_wdata_hi"), to("z_mux.zh_wdata_hi")),
        *[(f"zw_{p}{k}", w, frm(f"z_unit.zw_{p}{k}"), to(f"z_mux.zw_{p}{k}")) for p, w in (("we", 1), ("waddr", ABITS), ("wdata", 16))
          for k in range(4)],
        *[(f"mz_{p}{k}", w, frm(f"z_mux.mz_{p}{k}"), to(f"zbank{k}.{p}")) for p, w in (("we", 1), ("waddr", ABITS), ("wdata", 16))
          for k in range(4)],
        *[(f"z_raddr{k}", ABITS, frm(f"z_unit.z_raddr{k}"), to(f"zbank{k}.raddr")) for k in range(4)],
        *[(f"z_rdata{k}", 16, frm(f"zbank{k}.rdata"), to(f"z_unit.z_rdata{k}")) for k in range(4)],
        ("z_y", gpu.V, frm("z_unit.z_y"), to("gfx_sel.z_y")),
    ]
    return out


def design() -> dict:
    d = gpu.design()
    d.update({
        "id": "simt-gpu-gfx",
        "name": "SIMT GPU with graphics, stage G2d: video memory, a VGA display controller, gfx.cfg, pix with blending, a raster unit, a texture unit and a depth test",
        "createdAt": "2026-11-19T00:00:00.000Z",
        "blocks": BLOCKS,
        "nets": [
            {"id": f"n_{n:03d}", "name": name, "width": width, "driver": {"blockId": dr[0], "portId": dr[1]},
             "sinks": [{"blockId": blk, "portId": prt} for blk, prt in sinks],
             "kind": "bus" if width > 1 else "wire", "pipelineStage": 0}
            for n, (name, width, dr, sinks) in enumerate(wires(), 1)
        ],
        "topLevelPorts": TOP_PORTS,
    })
    return d


def main() -> None:
    fields = re.search(r"FIELDS = (\[.*?\])", (HERE / "golden" / "dx_reg.py").read_text(), re.S).group(1)
    assert eval(fields) == [f[0] for f in DX_FIELDS], "gfx/golden/dx_reg.py does not list the fields of DX_FIELDS"
    d = design()
    out = HERE / "design.json"
    out.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    print(f"{out}: {len(d['blocks'])} blocks, {len(d['nets'])} nets, {len(d['topLevelPorts'])} top-level ports")


if __name__ == "__main__":
    main()
