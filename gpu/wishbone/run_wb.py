"""Run kernels on the GPU through its Wishbone port, the way Caravel's management core would: every access is a Wishbone transfer
(cyc and stb held until ack, then the next), the program and data go in through the windows, the run starts with CTRL, the master
polls STATUS, and the results are read back through the global-memory window.

    python3 demos/simt-gpu/wishbone/run_wb.py [kernel ...] [--gaps] [-v]

--gaps puts random idle cycles between transfers. The bridge is the one in rtl/ (wb_bridge.v), or $WB_BRIDGE. Needs iverilog.
"""

from __future__ import annotations

import argparse
import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "model"))
import check_pipeline as cp  # noqa: E402
import run_kernel  # noqa: E402
import run_rtl  # noqa: E402
import simt  # noqa: E402

BRIDGE = Path(os.environ.get("WB_BRIDGE", HERE / "rtl" / "wb_bridge.v"))
M = 0xFFFFFFFF


def wb_address(host: int) -> int:
    """The Wishbone address of a host-bus address (the windows of caravel_gpu.v)."""
    if host >> 28 == 3:
        return 0x30000000 | host & 0xFFFF
    if host >> 28 == 1:
        return 0x30020000 | host & 0x1FFF
    if host >> 28 == 2:
        return 0x30030000 | host & 0xFFF
    if host < 0x800:
        return 0x30010000 | host
    raise ValueError(f"no Wishbone window for host address 0x{host:08x}")


TB = """`timescale 1ns/1ps
module tb;
  reg clk = 0, rst = 1;
  reg cyc = 0, stb = 0, we = 0;
  reg [3:0] sel = 0;
  reg [31:0] adr = 0, dat_i = 0;
  wire ack;
  wire [31:0] dat_o;
  wire [2:0] irq;
  wire running, done, error, diverged;
  caravel_gpu dut (.wb_clk_i(clk), .wb_rst_i(rst), .wbs_stb_i(stb), .wbs_cyc_i(cyc), .wbs_we_i(we), .wbs_sel_i(sel),
                   .wbs_dat_i(dat_i), .wbs_adr_i(adr), .wbs_ack_o(ack), .wbs_dat_o(dat_o), .user_irq(irq),
                   .gpu_running(running), .gpu_done(done), .gpu_error(error), .gpu_diverged(diverged));
  always #5 clk = ~clk;

  reg [63:0] writes [0:%(nw)d];
  reg [3:0] sels [0:%(nw)d];
  reg [31:0] reads [0:%(nr)d];
  integer i, run_cycles, gap, seed, waits;
  reg [31:0] got;
  reg seen_irq_done;

  // One Wishbone classic transfer: drive at the falling edge, hold cyc and stb until ack is seen, keep them through the
  // rising edge that completes the transfer, then release (a back-to-back master drives the next transfer at once).
  task xfer(input w, input [31:0] a, input [31:0] d, input [3:0] s, output [31:0] r);
    begin
      if (%(gaps)d) begin gap = $urandom_range(0, 3); repeat (gap) @(negedge clk); end
      @(negedge clk); cyc = 1; stb = 1; we = w; adr = a; dat_i = d; sel = s;
      waits = 0;
      @(negedge clk);
      while (!ack) begin @(negedge clk); waits = waits + 1; if (waits > 200) begin $display("HANG"); $finish; end end
      r = dat_o;
      @(posedge clk);
      #1 cyc = 0; stb = 0; we = 0; sel = 0;
    end
  endtask
  task wr(input [31:0] a, input [31:0] d); reg [31:0] unused; begin xfer(1, a, d, 4'hF, unused); end endtask
  task rd(input [31:0] a, output [31:0] r); begin xfer(0, a, 0, 4'hF, r); end endtask

  initial begin
    $readmemh("writes.hex", writes);
    $readmemh("reads.hex", reads);
    $readmemh("sels.hex", sels);
    repeat (3) @(negedge clk);
    rst = 0;
    @(negedge clk);
    for (i = 0; i < %(nw)d + 1; i = i + 1) xfer(1, writes[i][63:32], writes[i][31:0], sels[i], got);
    wr(32'h30000004, %(start)d);
    wr(32'h30000008, 0);
    wr(32'h30000000, 1);
    run_cycles = 0; seen_irq_done = 0;
    got = 0;
    while (!(got[1] || got[2]) && run_cycles < %(max)d) begin
      rd(32'h3000000C, got);
      run_cycles = run_cycles + 1;
    end
    if (got[2]) begin
      rd(32'h30000014, got); $display("ERROR %%0d %%0d", got[3:0], got[9:8]);
      rd(32'h30000010, got); $display("ERRPC %%0d", got);
    end else if (!got[1]) $display("TIMEOUT");
    else begin
      $display("DONE %%0d irq=%%b", run_cycles, irq);
      for (i = 0; i < %(nr)d; i = i + 1) begin rd(reads[i], got); $display("R %%0d %%0d", reads[i], got); end
    end
    $finish;
  end
endmodule
"""


def simulate(writes: list[tuple[int, int]], reads: list[int], start: int, gaps: bool = False, bridge: Path | None = None,
             sels: list[int] | None = None) -> str:
    """One run on the whole chip side: the master writes `writes` (Wishbone address, word), starts the core at `start`, polls STATUS,
    and reads `reads` back; `sels` gives each write's byte selects (default all four). Returns the testbench's output (DONE / ERROR / TIMEOUT / HANG lines and `R address value`)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "writes.hex").write_text("".join(f"{a:08x}{d:08x}\n" for a, d in writes))
        (tmp / "reads.hex").write_text("".join(f"{a:08x}\n" for a in reads) or "00000000\n")
        (tmp / "sels.hex").write_text("".join(f"{x:x}\n" for x in (sels or [15] * len(writes))))
        (tmp / "tb.v").write_text(TB % {"nw": len(writes) - 1, "nr": len(reads), "start": start, "max": 20000, "gaps": int(gaps)})
        files = [tmp / "tb.v", HERE / "caravel_gpu.v", bridge or BRIDGE, run_rtl.RTL / "top.v",
                 *sorted(p for p in run_rtl.RTL.glob("*.v") if p.name != "top.v")]
        built = subprocess.run(["iverilog", "-g2012", "-o", str(tmp / "sim"), *map(str, files)], capture_output=True, text=True)
        if built.returncode:
            raise AssertionError(f"iverilog failed:\n{built.stderr[:1500]}")
        return run_limited(tmp)


def run_on_wishbone(name: str, seed: int = 1, gaps: bool = False, verbose: bool = False) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        elf = run_kernel.compile_kernel(name, tmp)
        ref = simt.Gpu(simt.Config())
        syms = run_kernel.load_elf(ref, elf)
        inputs, expected = run_kernel.CASES[name](random.Random(seed))
        writes: list[tuple[int, int]] = []
        for addr, data in cp.elf_segments(elf):
            data = data + bytes(-len(data) % 4)
            writes += [(wb_address(addr + k), int.from_bytes(data[k:k + 4], "little")) for k in range(0, len(data), 4)]
        for sym, raw in inputs.items():
            raw = raw + bytes(-len(raw) % 4)
            writes += [(wb_address(syms[sym][0] + k), int.from_bytes(raw[k:k + 4], "little")) for k in range(0, len(raw), 4)]
            ref.write(syms[sym][0], raw)
        reads = [wb_address(syms[sym][0] + 4 * k) for sym, want in expected.items() for k in range(len(want))]
        out = simulate(writes, reads, syms["_start"][0], gaps)
        if "DONE" not in out:
            raise AssertionError(f"{name}: the run did not finish: {out.strip()[:300]}")
        polls = int(re.search(r"DONE (\d+) irq=(\d+)", out).group(1))
        irq = re.search(r"irq=(\d+)", out).group(1)
        got = {int(a): int(v) for a, v in re.findall(r"^R (\d+) (\d+)$", out, re.M)}
        ref.launch(syms["_start"][0])
        ref.run()
        for sym, want in expected.items():
            base = syms[sym][0]
            mine = [got[wb_address(base + 4 * k)] for k in range(len(want))]
            if mine != ref.read_words(base, len(want)) or mine != [w & M for w in want]:
                bad = next(k for k in range(len(want)) if mine[k] != want[k] & M)
                raise AssertionError(f"{name}: {sym}[{bad}] read through Wishbone 0x{mine[bad]:08x}, expected 0x{want[bad] & M:08x}")
        if verbose:
            print(f"  {name}: STATUS polled {polls} times; user_irq = {irq}")
        return {"polls": polls, "irq": irq}


def run_limited(tmp: Path) -> str:
    """vvp under the fuzzer's watchdog (memory, output and time limits)."""
    import fuzz_rtl
    out = fuzz_rtl.run_limited(["vvp", str(tmp / "sim")], tmp, max_seconds=300)
    if out is None:
        raise AssertionError("the simulation was killed by the watchdog")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kernels", nargs="*", default=list(run_kernel.CASES))
    ap.add_argument("--gaps", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    for name in args.kernels:
        run_on_wishbone(name, gaps=args.gaps, verbose=args.verbose)
        print(f"{name}: OK through Wishbone" + (" (random gaps)" if args.gaps else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
