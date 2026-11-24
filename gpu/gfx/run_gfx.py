"""Run a graphics kernel on the generated RTL of `simt-gpu-gfx` (gfx/rtl/ and the core's ../rtl/) under Icarus.

    python3 demos/simt-gpu/gfx/run_gfx.py [--rows=240] [--no-display] [--ppm=out.ppm]

The testbench is the host: it loads the kernel (kernels.kernel_g1b), starts it, waits for done, reads all of the video memory back
through the host window, then turns the display on and records one frame of the VGA output. The video memory must equal the
independent frame model (kernels.frame_g1b) and the instruction-level model's frame, and the displayed frame (640 x 480, every
pixel doubled) must show it: so the ROP's writes reached both copies of the video memory.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "model"))
import kernels  # noqa: E402
import simt  # noqa: E402

CORE_RTL, GFX_RTL = HERE.parent / "rtl", HERE / "rtl"
W, H = 320, 240

TB = r"""`timescale 1ns/1ps
module tb;
  reg clk = 0, rst = 1, host_en = 0, host_we = 0;
  reg [31:0] host_addr = 0, host_wdata = 0;
  wire [31:0] host_rdata; wire host_rvalid, running, done, error, diverged, hsync, vsync, de; wire [15:0] rgb;
  top dut(.clk(clk), .rst(rst), .host_en(host_en), .host_we(host_we), .host_addr(host_addr), .host_wdata(host_wdata),
          .host_rdata(host_rdata), .host_rvalid(host_rvalid), .running(running), .done(done), .error(error), .diverged(diverged),
          .hsync(hsync), .vsync(vsync), .de(de), .rgb(rgb));
  always #5 clk = ~clk;
  reg [31:0] code [0:%(ncode)d];
  integer i, cycles, o, shown, dc;
  reg [31:0] got;
  task hwrite(input [31:0] a, input [31:0] d);
    begin @(negedge clk); host_en = 1; host_we = 1; host_addr = a; host_wdata = d; @(negedge clk); host_en = 0; host_we = 0; end
  endtask
  task hread(input [31:0] a, output [31:0] d);
    begin @(negedge clk); host_en = 1; host_we = 0; host_addr = a; @(negedge clk); host_en = 0; #1 d = host_rdata; end
  endtask
  initial begin
    $readmemh("code.hex", code);
    o = $fopen("out.txt", "w");
    repeat (3) @(negedge clk);
    rst = 0;
    @(negedge clk);
    for (i = 0; i < %(ncode)d + 1; i = i + 1) hwrite(4 * i, code[i]);
    hwrite(32'h30000004, 0);
    hwrite(32'h30000008, 0);
    hwrite(32'h30000000, 1);
    cycles = 0;
    while (!done && !error && cycles < %(max)d) begin @(negedge clk); cycles = cycles + 1; end
    if (error) begin hread(32'h30000014, got); $fdisplay(o, "ERROR %%0d %%0d", got[3:0], got[9:8]); hread(32'h30000010, got); $fdisplay(o, "ERRPC %%0d", got); end
    else if (!done) $fdisplay(o, "TIMEOUT");
    else begin
      $fdisplay(o, "DONE %%0d", cycles);
      for (i = 0; i < %(words)d; i = i + 1) begin hread(32'h40000000 + 4 * i, got); $fdisplay(o, "R %%h", got); end
      if (%(display)d) begin
        hwrite(32'h30000020, 1);
        shown = 0; dc = 0;
        while (shown < 640 * 480 && dc < 3 * 800 * 525) begin
          @(negedge clk); dc = dc + 1;
          if (de) begin $fdisplay(o, "D %%h", rgb); shown = shown + 1; end
        end
      end
    end
    $fclose(o); $finish;
  end
endmodule
"""


def main() -> int:
    rows = int(next((a.split("=")[1] for a in sys.argv[1:] if a.startswith("--rows=")), H))
    display = "--no-display" not in sys.argv
    ppm = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--ppm=")), None)
    code = kernels.kernel_g1b(rows)
    want = kernels.frame_g1b(rows)
    ref = simt.Gpu(simt.Config())
    ref.write(0, code)
    ref.launch(0)
    ref.run(5_000_000)
    if ref.frame != want:
        print("FAIL: the instruction-level model and the frame model disagree")
        return 1
    names = {p.stem for p in GFX_RTL.glob("*.v")}
    files = [GFX_RTL / "top.v", *sorted(p for p in GFX_RTL.glob("*.v") if p.name != "top.v"),
             *sorted(p for p in CORE_RTL.glob("*.v") if p.name != "top.v" and p.stem not in names)]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        words = rows * W // 2
        (tmp / "code.hex").write_text("".join(f"{int.from_bytes(code[k:k + 4], 'little'):08x}\n" for k in range(0, len(code), 4)))
        (tmp / "tb.v").write_text(TB % {"ncode": len(code) // 4 - 1, "max": 3_000_000, "words": words, "display": int(display)})
        built = subprocess.run(["iverilog", "-g2012", "-o", str(tmp / "sim"), str(tmp / "tb.v"), *map(str, files)],
                               capture_output=True, text=True)
        if built.returncode:
            print(built.stderr[:3000])
            return 2
        subprocess.run(["vvp", "-n", str(tmp / "sim")], cwd=tmp, check=True, capture_output=True, timeout=7200)
        out = (tmp / "out.txt").read_text().split("\n")
    head = out[0]
    if not head.startswith("DONE"):
        print(f"FAIL: the core did not finish: {' '.join(out[:3])}")
        return 1
    cycles = int(head.split()[1])
    mem = [int(l.split()[1], 16) for l in out if l.startswith("R ")]
    px = [v >> 16 * h & 0xFFFF for v in mem for h in (0, 1)]
    bad = [p for p in range(rows * W) if px[p] != want[p]]
    ok = not bad
    print(f"G1b on the RTL: kernel done in {cycles} cycles; video memory {rows * W} pixels: "
          f"{'equal to the model' if ok else f'{len(bad)} differ, first (x {bad[0] % W}, y {bad[0] // W}): RTL 0x{px[bad[0]]:04x} model 0x{want[bad[0]]:04x}'}")
    if display:
        shown = [int(l.split()[1], 16) for l in out if l.startswith("D ")]
        intended = [want[(n // 640 >> 1) * W + (n % 640 >> 1)] if (n // 640 >> 1) < rows else None for n in range(640 * 480)]
        diff = [n for n in range(min(len(shown), 640 * 480)) if intended[n] is not None and shown[n] != intended[n]]
        good = len(shown) >= 640 * 480 and not diff
        ok &= good
        print(f"  display: {len(shown)} visible pixels recorded, {'the frame shows the model' if good else f'{len(diff)} differ'}")
        if ppm:
            body = bytearray()
            for p in shown[:640 * 480]:
                body += bytes(((p >> 11 & 31) * 255 // 31, (p >> 5 & 63) * 255 // 63, (p & 31) * 255 // 31))
            Path(ppm).write_bytes(b"P6 640 480 255\n" + bytes(body))
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
