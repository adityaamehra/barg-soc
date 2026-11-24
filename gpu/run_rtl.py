"""Run the six kernels on the generated Verilog (rtl/*.v, wired by rtl/top.v) under Icarus, through the host bus, and compare
with the instruction-level model and the Python references.

    python3 demos/simt-gpu/run_rtl.py [kernel ...] [-v] [--gfx]

The testbench is the host: it resets the core, writes the instruction memory and the kernel's inputs word by word, writes
START_PC and CTRL, waits for done (or error), then reads the outputs back through the same bus. Needs iverilog and the
files export_rtl.py writes.
"""

from __future__ import annotations

import argparse
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "model"))
import check_pipeline as cp  # noqa: E402
import run_kernel  # noqa: E402
import simt  # noqa: E402

RTL = HERE / "rtl"
GFX_RTL = HERE / "gfx" / "rtl"
GFX = False      # --gfx: the graphics design (gfx/rtl/top.v and its blocks, the core's other blocks from rtl/)
M = 0xFFFFFFFF


def rtl_files() -> list[Path]:
    if not GFX:
        return [RTL / "top.v", *sorted(p for p in RTL.glob("*.v") if p.name != "top.v")]
    names = {p.stem for p in GFX_RTL.glob("*.v")}
    return [GFX_RTL / "top.v", *sorted(p for p in GFX_RTL.glob("*.v") if p.name != "top.v"),
            *sorted(p for p in RTL.glob("*.v") if p.name != "top.v" and p.stem not in names)]
TB = """`timescale 1ns/1ps
module tb;
  reg clk = 0, rst = 1;
  reg host_en = 0, host_we = 0;
  reg [31:0] host_addr = 0, host_wdata = 0;
  wire [31:0] host_rdata;
  wire host_rvalid, running, done, error, diverged;
  top dut (.clk(clk), .rst(rst), .host_en(host_en), .host_we(host_we), .host_addr(host_addr), .host_wdata(host_wdata),
           .host_rdata(host_rdata), .host_rvalid(host_rvalid), .running(running), .done(done), .error(error),
           .diverged(diverged));
  always #5 clk = ~clk;

  reg [63:0] writes [0:%(nw)d];
  reg [31:0] reads [0:%(nr)d];
  integer i, cycles, ndiv;
  reg [31:0] got;

  task hwrite(input [31:0] a, input [31:0] d);
    begin
      @(negedge clk); host_en = 1; host_we = 1; host_addr = a; host_wdata = d;
      @(negedge clk); host_en = 0; host_we = 0;
    end
  endtask
  task hread(input [31:0] a, output [31:0] d);
    begin
      @(negedge clk); host_en = 1; host_we = 0; host_addr = a;
      @(negedge clk); host_en = 0;
      #1 d = host_rdata;
    end
  endtask

%(trace)s
  initial begin
    $readmemh("writes.hex", writes);
    $readmemh("reads.hex", reads);
    repeat (3) @(negedge clk);
    rst = 0;
    @(negedge clk);
    for (i = 0; i < %(nw)d + 1; i = i + 1) hwrite(writes[i][63:32], writes[i][31:0]);
    hwrite(32'h30000004, %(start)d);
    hwrite(32'h30000008, 0);
    hwrite(32'h30000000, 1);
    cycles = 0; ndiv = 0;
    while (!done && !error && cycles < %(max)d) begin
      @(negedge clk); cycles = cycles + 1;
      if (diverged) ndiv = ndiv + 1;
    end
    if (error) begin
      hread(32'h30000014, got); $display("ERROR %%0d %%0d", got[3:0], got[9:8]);
      hread(32'h30000010, got); $display("ERRPC %%0d", got);
    end else if (!done) $display("TIMEOUT");
    else begin
      $display("DONE %%0d %%0d", cycles, ndiv);
      for (i = 0; i < %(nr)d; i = i + 1) begin hread(reads[i], got); $display("R %%0d %%0d", reads[i], got); end
    end
    $finish;
  end
endmodule
"""


COMMITS = '''  always @(posedge clk) if (dut.u_pipe_ctrl.advance && dut.u_dx_reg.valid_out) $display("C %0d %0d %0d %0d", dut.u_dx_reg.wid_out, dut.u_dx_reg.pc_out, dut.u_wb_mux.we0, dut.u_wb_mux.wdata0);'''

TRACE = '''  always @(negedge clk) if (running && cycles < 60) $display("T %0d fire=%b fwid=%0d selpc=%h fetch=%0d inst=%h adv=%b stall=%b act=%b infl=%b",
      cycles, dut.net_n_019_fire, dut.net_n_020_fwid, dut.net_n_021_sel_pc, dut.net_n_024_fetch_idx, dut.net_n_030_rdata,
      dut.net_n_126_advance, dut.net_n_025_stall, dut.net_n_016_active, dut.net_n_017_inflight);'''


def run_on_rtl(name: str, seed: int = 1, verbose: bool = False, trace: bool = False) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        elf = run_kernel.compile_kernel(name, tmp)
        ref = simt.Gpu(simt.Config())
        syms = run_kernel.load_elf(ref, elf)
        segments = cp.elf_segments(elf)
        inputs, expected = run_kernel.CASES[name](random.Random(seed))
        writes: list[tuple[int, int]] = []
        for addr, data in segments:
            data = data + bytes(-len(data) % 4)
            writes += [(addr + k, int.from_bytes(data[k:k + 4], "little")) for k in range(0, len(data), 4)]
        for sym, raw in inputs.items():
            raw = raw + bytes(-len(raw) % 4)
            writes += [(syms[sym][0] + k, int.from_bytes(raw[k:k + 4], "little")) for k in range(0, len(raw), 4)]
            ref.write(syms[sym][0], raw)
        in_reads = [syms[sym][0] + 4 * k for sym, raw in inputs.items() for k in range((len(raw) + 3) // 4)]
        reads = in_reads + [syms[sym][0] + 4 * k for sym, want in expected.items() for k in range(len(want))]
        (tmp / "writes.hex").write_text("".join(f"{a:08x}{d:08x}\n" for a, d in writes))
        (tmp / "reads.hex").write_text("".join(f"{a:08x}\n" for a in reads))
        (tmp / "tb.v").write_text(TB % {"nw": len(writes) - 1, "nr": len(reads), "start": syms["_start"][0], "max": 400_000, "trace": (trace if isinstance(trace, str) and trace.startswith("  always") else COMMITS if trace == "commits" else TRACE) if trace else ""})
        files = [tmp / "tb.v", *rtl_files()]
        built = subprocess.run(["iverilog", "-g2012", "-o", str(tmp / "sim"), *map(str, files)], capture_output=True, text=True)
        if built.returncode != 0:
            raise AssertionError(f"{name}: iverilog failed:\n{built.stderr[:1500]}")
        sim = subprocess.run(["vvp", str(tmp / "sim")], cwd=tmp, capture_output=True, text=True, timeout=1800)
        out = sim.stdout
        if trace == "commits":
            return {"commits": [tuple(map(int, l.split()[1:])) for l in out.splitlines() if l.startswith("C ")]}
        if trace:
            print("\n".join(l for l in out.splitlines() if l.startswith("T ")))
        if "ERROR" in out or "TIMEOUT" in out or "DONE" not in out:
            raise AssertionError(f"{name}: the core did not finish: {out.strip()[:300]}")
        cycles = int(re.search(r"DONE (\d+)", out).group(1))
        got = {int(a): int(v) for a, v in re.findall(r"^R (\d+) (\d+)$", out, re.M)}
        for sym, raw in inputs.items():          # the inputs must still be there: the host path and the banks
            padded = raw + bytes(-len(raw) % 4)
            back = [got[syms[sym][0] + 4 * k] for k in range(len(padded) // 4)]
            if back != [int.from_bytes(padded[4 * k:4 * k + 4], "little") for k in range(len(padded) // 4)]:
                bad = next(k for k in range(len(back)) if back[k] != int.from_bytes(padded[4 * k:4 * k + 4], "little"))
                raise AssertionError(f"{name}: input {sym}[{bad}] read back as 0x{back[bad]:08x} after the run")
        ref.launch(syms["_start"][0])
        ref.run()
        for sym, want in expected.items():
            base = syms[sym][0]
            mine = [got[base + 4 * k] for k in range(len(want))]
            model = ref.read_words(base, len(want))
            if mine != model:
                bad = next(k for k in range(len(want)) if mine[k] != model[k])
                raise AssertionError(f"{name}: {sym}[{bad}] RTL 0x{mine[bad]:08x}, model 0x{model[bad]:08x}")
            if mine != [w & M for w in want]:
                raise AssertionError(f"{name}: {sym} differs from the Python reference")
        if verbose:
            print(f"  {name}: {cycles} cycles on the RTL, {ref.stats.steps} warp instructions in the model")
        return {"cycles": cycles, "steps": ref.stats.steps}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kernels", nargs="*", default=list(run_kernel.CASES))
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--gfx", action="store_true", help="run on the graphics design, gfx/rtl/ over rtl/")
    args = ap.parse_args()
    global GFX
    GFX = args.gfx
    for name in args.kernels:
        r = run_on_rtl(name, verbose=args.verbose, trace=args.trace)
        print(f"{name}: OK on the generated RTL ({r['cycles']} cycles)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
