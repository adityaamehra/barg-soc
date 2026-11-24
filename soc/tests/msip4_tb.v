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
// Runs demos/quad-soc/tests/msip4.S (image from +HEX=<file>) on the quad-core SoC.
// Expected: round count (word 0x480) = 10, flag (word 0x481) = 0x600D.
module msip4_tb;
`include "memview.vh"
  reg clk = 0, rst = 1;
  reg meip = 0, rx_valid = 0;
  reg [7:0] rx_data = 0;
  reg [31:0] plic_rdata = 0;
  wire uart_irq, uart_tx_valid, plic_we, plic_re;
  wire [7:0] uart_tx_data;
  integer cyc, limit;
  reg [1023:0] hexfile;
  top dut (.clk(clk), .rst(rst), .rx_valid(rx_valid), .rx_data(rx_data), .ext_s2(1'b0), .ext_s3(1'b0), .meip(meip), `PPINS);
  always #5 clk = ~clk;
  initial begin
    if (!$value$plusargs("HEX=%s", hexfile)) hexfile = "msip4.hex";
    if (!$value$plusargs("LIMIT=%d", limit)) limit = 400000;
    $readmemh(hexfile, dut.u_ram_main.u_ip.mem);
    repeat (3) @(posedge clk);
    rst <= 0;   // non-blocking: the core must still see reset at this edge
    for (cyc = 0; cyc < limit && `RAMW(32'h481) !== 32'h600D; cyc = cyc + 1) @(posedge clk);
    $display("after %0d cycles: rounds %0d, flag %h", cyc, `RAMW(32'h480), `RAMW(32'h481));
    if (`RAMW(32'h480) === 32'd10 && `RAMW(32'h481) === 32'h600D)
      $display("PASS msip ping-pong: 10 rounds between harts 0 and 1");
    else $display("FAIL msip ping-pong: rounds %0d, flag %h (want 10 and 600d)", `RAMW(32'h480), `RAMW(32'h481));
    $finish;
  end
endmodule
