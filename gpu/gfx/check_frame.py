"""Stage G1a check: video memory through the host bus, and whole frames out of the display controller, on the generated RTL.

    python3 demos/simt-gpu/gfx/check_frame.py [--frames=2] [--ppm=out.ppm]

The testbench is the host: after reset it writes a random 320 x 240 image into the video memory word by word (0x4000_0000),
reads words back, reads DISP_CTRL, DISP_STATUS and the core's STATUS, turns the display on, lets it run for whole frames, and
reads DISP_STATUS again. Every cycle it records host_rdata, hsync, vsync, de and rgb. The same host-bus trace is run through the
golden models (gfx_host, disp_ctrl, and the memory banks as their storage choices say), and the two records must be identical
cycle by cycle. Needs iverilog and the files export_gfx.py writes (gfx/rtl/) plus the core's ../rtl/.
"""

from __future__ import annotations

import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE / "golden"))
from disp_ctrl import DispCtrl  # noqa: E402
from gfx_host import GfxHost  # noqa: E402

CORE_RTL, GFX_RTL = HERE.parent / "rtl", HERE / "rtl"
W, H, DEPTH = 320, 240, 19200
FRAME = 800 * 525
RESET = 2


def commands(seed=1, frames=2):
    rnd = random.Random(seed)
    image = [rnd.getrandbits(16) for _ in range(W * H)]
    cmds = [(1, 1, 0x4000_0000 + 2 * p, image[p + 1] << 16 | image[p]) for p in range(0, W * H, 2)]
    reads = [0x4000_0000 + 4 * rnd.randrange(W * H // 2) for _ in range(64)]
    reads += [0x3000_0020, 0x3000_0024, 0x3000_000C, 0x4002_5800, 0x4000_0002, 0x5000_0000]
    for a in reads:
        cmds += [(1, 0, a, 0), (0, 1, 0, 1)]
    cmds += [(1, 1, 0x3000_0020, 1), (1, 0, 0x3000_0020, 0), (0, 1, 0, 1)]
    cmds += [(0, 1, 0, frames * FRAME + 1000), (1, 0, 0x3000_0024, 0), (0, 1, 0, 2),
             (1, 1, 0x3000_0020, 0), (0, 1, 0, 10), (1, 0, 0x3000_0024, 0), (0, 1, 0, 2)]
    return image, cmds


def cycles(cmds):
    """The host bus, one dict per cycle (reset cycles first)."""
    for _ in range(RESET):
        yield {"rst": 1, "host_en": 0, "host_we": 0, "host_addr": 0, "host_wdata": 0}
    for en, we, addr, data in cmds:
        if en:
            yield {"rst": 0, "host_en": 1, "host_we": we, "host_addr": addr, "host_wdata": data}
        else:
            for _ in range(data):
                yield {"rst": 0, "host_en": 0, "host_we": 0, "host_addr": 0, "host_wdata": 0}


def model(cmds):
    host, disp = GfxHost(), DispCtrl()
    vw, vd = [[0] * DEPTH for _ in range(4)], [[0] * DEPTH for _ in range(4)]
    vw_q, vd_q = [0] * 4, [0] * 4
    out = []
    for i in cycles(cmds):
        hi = dict(i, core_rdata=0, **{f"vw_rdata{k}": vw_q[k] for k in range(4)})
        dpre = disp.outputs({f"vd_rdata{k}": vd_q[k] for k in range(4)})
        hi.update(vblank=dpre["vblank"] or 0, frame=dpre["frame"] or 0)
        ho = host.outputs(hi)
        en = ho["disp_en"] or 0
        di = {"rst": i["rst"], "enable": en, **{f"vd_rdata{k}": vd_q[k] for k in range(4)}}
        do = disp.outputs(di)
        out.append((ho["host_rdata"], do["hsync"], do["vsync"], do["de"], do["rgb"]))
        vw_q = [vw[k][ho["vw_raddr"]] if ho["vw_raddr"] < DEPTH else 0 for k in range(4)]
        vd_q = [vd[k][do["vd_raddr"]] if do["vd_raddr"] is not None and do["vd_raddr"] < DEPTH else 0 for k in range(4)]
        for k in range(4):
            if ho[f"v_we{k}"] and ho["v_waddr"] < DEPTH:
                vw[k][ho["v_waddr"]] = vd[k][ho["v_waddr"]] = ho["v_wdata_lo" if k % 2 == 0 else "v_wdata_hi"]
        host.edge(hi)
        disp.edge(di)
    return out


TB = r"""
`timescale 1ns/1ps
module tb;
  reg clk = 0, rst = 1, host_en = 0, host_we = 0;
  reg [31:0] host_addr = 0, host_wdata = 0;
  wire [31:0] host_rdata; wire host_rvalid, running, done, error, diverged, hsync, vsync, de; wire [15:0] rgb;
  %(top)s dut(.clk(clk), .rst(rst), .host_en(host_en), .host_we(host_we), .host_addr(host_addr), .host_wdata(host_wdata),
      .host_rdata(host_rdata), .host_rvalid(host_rvalid), .running(running), .done(done), .error(error), .diverged(diverged),
      .hsync(hsync), .vsync(vsync), .de(de), .rgb(rgb));
  always #5 clk = ~clk;
  integer f, o, n, en, we, a, d, k;
  task cycle; begin #4 $fwrite(o, "%%h %%b%%b%%b %%h\n", host_rdata, hsync, vsync, de, rgb); #6; end endtask
  initial begin
    f = $fopen("%(cmds)s", "r"); o = $fopen("%(rec)s", "w");
    for (k = 0; k < %(reset)d; k = k + 1) cycle;
    rst = 0;
    while (!$feof(f)) begin
      n = $fscanf(f, "%%h %%h %%h %%h\n", en, we, a, d);
      if (n == 4) begin
        if (en) begin host_en = 1; host_we = we; host_addr = a; host_wdata = d; cycle; end
        else begin host_en = 0; host_we = 0; host_addr = 0; host_wdata = 0; for (k = 0; k < d; k = k + 1) cycle; end
      end
    end
    $fclose(o); $finish;
  end
endmodule
"""


def main() -> int:
    frames = int(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--frames=")), 2))
    ppm = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--ppm=")), None)
    image, cmds = commands(frames=frames)
    top_v = (GFX_RTL / "top.v").read_text(encoding="utf-8")
    top = re.search(r"module\s+(\w+)", top_v).group(1)
    gfx_names = {p.stem for p in GFX_RTL.glob("*.v")}
    files = [GFX_RTL / "top.v", *sorted(p for p in GFX_RTL.glob("*.v") if p.name != "top.v"),
             *sorted(p for p in CORE_RTL.glob("*.v") if p.name != "top.v" and p.stem not in gfx_names)]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "cmds.txt").write_text("".join(f"{e:x} {w:x} {a:x} {d:x}\n" for e, w, a, d in cmds))
        (tmp / "tb.v").write_text(TB % {"top": top, "cmds": tmp / "cmds.txt", "rec": tmp / "rec.txt", "reset": RESET})
        built = subprocess.run(["iverilog", "-g2012", "-o", str(tmp / "sim"), str(tmp / "tb.v"), *map(str, files)],
                               capture_output=True, text=True)
        if built.returncode:
            print(built.stderr[:3000])
            return 2
        subprocess.run(["vvp", "-n", str(tmp / "sim")], check=True, capture_output=True)
        rec = (tmp / "rec.txt").read_text().split("\n")[:-1]
    want = model(cmds)
    # the golden models themselves against the intent: the first frame shows the image, each pixel doubled both ways
    shown_first = [w[4] for w in want if w[3] == 1][:640 * 480]
    intended = [image[(n // 640 >> 1) * W + (n % 640 >> 1)] for n in range(640 * 480)]
    if shown_first != intended:
        print("FAIL: the golden models do not show the written image")
        return 1
    if len(rec) != len(want):
        print(f"FAIL: {len(rec)} cycles recorded, {len(want)} expected")
        return 1
    bad, prev_read, cyc_fail = 0, False, []
    flat = [c for c in cycles(cmds)]
    for n, (line, (rd, hs, vs, de, rgb)) in enumerate(zip(rec, want)):
        got_rd, syncs, got_rgb = line.split()
        bit = lambda c: int(c) if c in "01" else None  # noqa: E731  (x before the first reset edge, as the models' None)
        got = (bit(syncs[0]), bit(syncs[1]), bit(syncs[2]), int(got_rgb, 16) if "x" not in got_rgb.lower() else None)
        exp = (hs, vs, de, rgb)
        ok = all(e is None or g == e for g, e in zip(got, exp))  # None: the models' undefined value before reset
        if prev_read and ("x" in got_rd.lower() or int(got_rd, 16) != rd):
            ok = False
        if not ok:
            bad += 1
            if len(cyc_fail) < 8:
                cyc_fail.append(f"cycle {n}: got rdata {got_rd} sync/de/rgb {got}; want rdata {hex(rd) if rd is not None else None} {exp}")
        prev_read = flat[n]["host_en"] == 1 and flat[n]["host_we"] == 0
    if ppm:
        pixels = [int(line.split()[2], 16) for line, w in zip(rec, want) if w[3] == 1][:640 * 480]
        body = bytearray()
        for p in pixels:
            body += bytes(((p >> 11 & 31) * 255 // 31, (p >> 5 & 63) * 255 // 63, (p & 31) * 255 // 31))
        Path(ppm).write_bytes(b"P6 640 480 255\n" + bytes(body))
    shown = sum(1 for w in want if w[3] == 1)
    print(f"{len(rec)} cycles, {shown} visible pixels ({shown // (640 * 480)} frames), host reads checked; "
          f"{'PASS' if not bad else f'FAIL: {bad} cycles differ'}")
    for line in cyc_fail:
        print("  " + line)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
