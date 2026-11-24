`ifdef PS2
`define PS2TIE , .ps2k_clk_i(1'b1), .ps2k_dat_i(1'b1), .ps2m_clk_i(1'b1), .ps2m_dat_i(1'b1)
`else
`define PS2TIE
`endif
`ifdef PERIPH
`define PPINS .gpio_in(16'd0), .spi_miso(1'b0), .i2c_scl_i(1'b1), .i2c_sda_i(1'b1) `PS2TIE
`else
`define PPINS .periph_rdata(32'd0)
`endif
// Runs a bare-metal image on the quad-core SoC with the GPU cluster until the program writes TOHOST (word 0x3FFC00, address 0x80FFF000).
// Plusargs: +HEX=<image>, +LIMIT=<cycles>. Prints "TOHOST <value> <cycles>" (1 = pass; an odd value > 1 is a failure code * 2 + 1).
module gpu_tb;
`include "memview.vh"
  reg clk = 0, rst = 1;
  reg meip = 0, rx_valid = 0, s2 = 0, s3 = 0;
  reg [7:0] rx_data = 0;
  wire uart_irq, uart_tx_valid, gpu_running, gpu_done, gpu_error, gpu_diverged;
  wire [7:0] uart_tx_data;
  integer cyc, limit;
  reg [31:0] lo, hi;
  integer i;
  reg [1023:0] hexfile, outdir, fn;
  top dut (.clk(clk), .rst(rst), .rx_valid(rx_valid), .rx_data(rx_data), .ext_s2(s2), .ext_s3(s3), .meip(meip), `PPINS,
           .uart_irq(uart_irq), .uart_tx_valid(uart_tx_valid), .uart_tx_data(uart_tx_data),
           .gpu_running(gpu_running), .gpu_done(gpu_done), .gpu_error(gpu_error), .gpu_diverged(gpu_diverged));
  always #5 clk = ~clk;
  initial begin
    if (!$value$plusargs("HEX=%s", hexfile)) hexfile = "image.hex";
    if (!$value$plusargs("LIMIT=%d", limit)) limit = 2000000;
    $readmemh(hexfile, dut.u_ram_main.u_ip.mem);
    repeat (3) @(posedge clk);
    rst <= 0;   // non-blocking: the core must still see reset at this edge
    for (cyc = 0; cyc < limit && `RAMW(32'h3FFC00) === 32'd0; cyc = cyc + 1) @(posedge clk);
    $display("TOHOST %0d %0d", `RAMW(32'h3FFC00), cyc);
    // +LO=<word index> +HI=<word index>: print the nonzero RAM words in that range ("W <index> <value>"), for diagnosis
    if ($value$plusargs("LO=%h", lo) && $value$plusargs("HI=%h", hi))
      for (i = lo; i <= hi; i = i + 1) if (`RAMW(i) !== 32'd0) $display("W %0h %0h", i, `RAMW(i));
`ifdef DUMPFRAMES
    // +OUT=<directory>: every core's video memory (work copy), bank by bank, as f<core>_<bank>.hex; the include is written by gfx_tests.py
    if ($value$plusargs("OUT=%s", outdir)) begin
`include "dump_frames.vh"
    end
`endif
    $finish;
  end
endmodule
