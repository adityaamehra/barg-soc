"""Stage G2a: the software triangle kernel (gfx/sw/tri.c) on the instruction-level model and on the generated RTL, against the
frame model of gfx/scenes.py, with the cycles per pixel that G2b's raster unit must beat.

    python3 demos/simt-gpu/gfx/run_g2a.py [scene ...] [--kernel=tri|tri_rast] [--iss-only] [--display] [--ppm=DIR]

--kernel=tri_rast runs G2b's kernel (the raster unit) on the same scenes; the frames must be the same.

The testbench is the host: it writes the kernel's code and data and the scene through the host bus, starts it at _start, waits
for done, and reads all of the video memory back through the host window (0x4000_0000). With --display it also records one
displayed frame (640 x 480, every pixel doubled), which must show the same image.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "model"))
sys.path.insert(0, str(HERE))
import check_pipeline as cp  # noqa: E402
import run_kernel  # noqa: E402
import scenes  # noqa: E402
import simt  # noqa: E402

CORE_RTL, GFX_RTL = HERE.parent / "rtl", HERE / "rtl"
W, H = 320, 240
MAX_CYCLES = 20_000_000

TB = r"""`timescale 1ns/1ps
module tb;
  reg clk = 0, rst = 1, host_en = 0, host_we = 0;
  reg [31:0] host_addr = 0, host_wdata = 0;
  wire [31:0] host_rdata; wire host_rvalid, running, done, error, diverged, hsync, vsync, de; wire [15:0] rgb;
  top dut(.clk(clk), .rst(rst), .host_en(host_en), .host_we(host_we), .host_addr(host_addr), .host_wdata(host_wdata),
          .host_rdata(host_rdata), .host_rvalid(host_rvalid), .running(running), .done(done), .error(error), .diverged(diverged),
          .hsync(hsync), .vsync(vsync), .de(de), .rgb(rgb));
  always #5 clk = ~clk;
  reg [63:0] writes [0:%(nw)d];
  integer i, cycles, o, shown, dc;
  reg [31:0] got;
  task hwrite(input [31:0] a, input [31:0] d);
    begin @(negedge clk); host_en = 1; host_we = 1; host_addr = a; host_wdata = d; @(negedge clk); host_en = 0; host_we = 0; end
  endtask
  task hread(input [31:0] a, output [31:0] d);
    begin @(negedge clk); host_en = 1; host_we = 0; host_addr = a; @(negedge clk); host_en = 0; #1 d = host_rdata; end
  endtask
  initial begin
    $readmemh("writes.hex", writes);
    o = $fopen("out.txt", "w");
    repeat (3) @(negedge clk);
    rst = 0;
    @(negedge clk);
    for (i = 0; i < %(nw)d + 1; i = i + 1) hwrite(writes[i][63:32], writes[i][31:0]);
    hwrite(32'h30000004, %(start)d);
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


def scene_bytes(syms, clear, tris, tex=None, zclear=None):
    import struct
    if len(tris) > scenes.MAXT:
        raise ValueError("too many triangles")
    flat = [v for t in tris for v in t]
    extra = {} if tex is None else {0x5000_0000: b"".join(struct.pack("<H", p) for p in tex)}
    if zclear is not None:
        extra[0x4004_0000] = struct.pack("<H", zclear) * (W * H)
    return {**extra, syms["ntri"][0]: struct.pack("<i", len(tris)), syms["clear"][0]: struct.pack("<I", clear),
            syms["tri"][0]: b"".join(struct.pack("<I", v & 0xFFFFFFFF) for v in flat)}


def ppm(path: Path, px: list[int], w: int, h: int) -> None:
    body = bytearray()
    for p in px[:w * h]:
        body += bytes(((p >> 11 & 31) * 255 // 31, (p >> 5 & 63) * 255 // 63, (p & 31) * 255 // 31))
    path.write_bytes(f"P6 {w} {h} 255\n".encode() + bytes(body))


def main() -> int:
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or list(scenes.SCENES)
    iss_only, display = "--iss-only" in sys.argv, "--display" in sys.argv
    kernel = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--kernel=")), "tri")
    ppm_dir = next((Path(a.split("=", 1)[1]) for a in sys.argv[1:] if a.startswith("--ppm=")), None)
    if "clear" not in names and not iss_only:
        names = ["clear", *names]                       # the clear-only scene's cycles are subtracted from the others'
    scenes.self_check()
    gfx_names = {p.stem for p in GFX_RTL.glob("*.v")}
    files = [GFX_RTL / "top.v", *sorted(p for p in GFX_RTL.glob("*.v") if p.name != "top.v"),
             *sorted(p for p in CORE_RTL.glob("*.v") if p.name != "top.v" and p.stem not in gfx_names)]
    ok, cycles_of = True, {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        elf = tmp / f"{kernel}.elf"
        subprocess.run([run_kernel.GCC, *run_kernel.CFLAGS, "-Werror=frame-larger-than=112", "-T", str(HERE.parent / "sw" / "link.ld"),
                        str(HERE.parent / "sw" / "crt0.S"), str(HERE / "sw" / f"{kernel}.c"), "-o", str(elf)], check=True)
        for name in names:
            clear, tris = scenes.scene(name)
            tex = scenes.texture(name)
            zclear = scenes.depth_clear(name)
            want = scenes.frame(clear, tris, tex, zclear)
            ref = simt.Gpu(simt.Config())
            syms = run_kernel.load_elf(ref, elf)
            data = scene_bytes(syms, clear, tris, tex, zclear)
            for a, raw in data.items():
                ref.write(a, raw)
            ref.launch(syms["_start"][0])
            ref.run(50_000_000)
            iss_ok = ref.frame == want
            ok &= iss_ok
            line = f"{name:8} {len(tris):2} triangles: model {'equal' if iss_ok else 'DIFFERENT'} ({ref.stats.steps} warp instructions)"
            if iss_only:
                print(line)
                continue
            writes = []
            for addr, seg in cp.elf_segments(elf):
                seg = seg + bytes(-len(seg) % 4)
                writes += [(addr + k, int.from_bytes(seg[k:k + 4], "little")) for k in range(0, len(seg), 4)]
            for a, raw in data.items():
                writes += [(a + k, int.from_bytes(raw[k:k + 4], "little")) for k in range(0, len(raw), 4)]
            run = tmp / name
            run.mkdir()
            (run / "writes.hex").write_text("".join(f"{a:08x}{d:08x}\n" for a, d in writes))
            (run / "tb.v").write_text(TB % {"nw": len(writes) - 1, "start": syms["_start"][0], "max": MAX_CYCLES,
                                            "words": W * H // 2, "display": int(display)})
            built = subprocess.run(["iverilog", "-g2012", "-o", str(run / "sim"), str(run / "tb.v"), *map(str, files)],
                                   capture_output=True, text=True)
            if built.returncode:
                print(built.stderr[:3000])
                return 2
            subprocess.run(["vvp", "-n", str(run / "sim")], cwd=run, check=True, capture_output=True, timeout=4 * 3600)
            out = (run / "out.txt").read_text().split("\n")
            if not out[0].startswith("DONE"):
                print(f"{line}; RTL did not finish: {' '.join(out[:3])}")
                ok = False
                continue
            cyc = cycles_of[name] = int(out[0].split()[1])
            mem = [int(l.split()[1], 16) for l in out if l.startswith("R ")]
            px = [v >> 16 * h & 0xFFFF for v in mem for h in (0, 1)]
            bad = [p for p in range(W * H) if px[p] != want[p]]
            ok &= not bad
            line += f"; RTL {cyc} cycles, video memory " + ("equal" if not bad else
                    f"{len(bad)} differ, first (x {bad[0] % W}, y {bad[0] // W}) RTL 0x{px[bad[0]]:04x} model 0x{want[bad[0]]:04x}")
            if name != "clear" and "clear" in cycles_of:
                cov, box = scenes.covered(tris), scenes.bbox_pixels(tris)
                net = cyc - cycles_of["clear"]
                line += f"; {net / max(cov, 1):.1f} cycles per covered pixel, {net / max(box, 1):.2f} per box pixel"
            if display:
                shown = [int(l.split()[1], 16) for l in out if l.startswith("D ")]
                intended = [want[(n // 640 >> 1) * W + (n % 640 >> 1)] for n in range(640 * 480)]
                good = shown[:640 * 480] == intended
                ok &= good
                line += f"; display {'shows it' if good else 'DIFFERENT'}"
                if ppm_dir:
                    ppm(ppm_dir / f"{kernel}-{name}.ppm", shown, 640, 480)
            elif ppm_dir:
                ppm(ppm_dir / f"{kernel}-{name}.ppm", px, W, H)
            print(line, flush=True)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
