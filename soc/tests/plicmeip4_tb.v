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
// Drives plicmeip4.S on the quad-core SoC: raises ext_s2 and ext_s3 once all four harts are ready, holds each level until its claim is
// recorded, releases both and lets the handlers complete, then raises ext_s2 again (it must interrupt hart 2 a second time, so complete
// really cleared the source's in-service state) and releases it. Prints the nonzero words 0x540..0x55f ("W <index> <value>") and END.
module plicmeip4_tb;
`include "memview.vh"
  reg clk = 0, rst = 1;
  reg meip = 0, rx_valid = 0, s2 = 0, s3 = 0;
  reg [7:0] rx_data = 0;
  wire uart_irq, uart_tx_valid;
  wire [7:0] uart_tx_data;
  integer cyc, limit, i;
  reg [1023:0] hexfile;
  top dut (.clk(clk), .rst(rst), .rx_valid(rx_valid), .rx_data(rx_data), .ext_s2(s2), .ext_s3(s3), .meip(meip), `PPINS,
           .uart_irq(uart_irq), .uart_tx_valid(uart_tx_valid), .uart_tx_data(uart_tx_data));
  always #5 clk = ~clk;
  task waitfor(input [31:0] idx, input [31:0] val);
    begin
      while (cyc < limit && `RAMW(idx) !== val) begin @(posedge clk); cyc = cyc + 1; end
    end
  endtask
  initial begin
    if (!$value$plusargs("HEX=%s", hexfile)) hexfile = "image.hex";
    if (!$value$plusargs("LIMIT=%d", limit)) limit = 300000;
    $readmemh(hexfile, dut.u_ram_main.u_ip.mem);
    cyc = 0;
    repeat (3) @(posedge clk);
    rst <= 0;   // non-blocking: the core must still see reset at this edge
    waitfor(32'h540, 32'd4);                 // all four harts configured
    repeat (50) @(posedge clk);
    s2 = 1; s3 = 1;
    waitfor(32'h54a, 32'd1);                 // hart 2 took it
    waitfor(32'h54b, 32'd1);                 // hart 3 took it
    repeat (300) @(posedge clk);             // time for a wrong hart to take it too
    s2 = 0; s3 = 0;
    `RAMPOKE(32'h550, 32'd1);
    waitfor(32'h558, 32'd2);                 // both completed
    repeat (100) @(posedge clk);
    `RAMPOKE(32'h550, 32'd0);
    s2 = 1;
    waitfor(32'h54a, 32'd2);                 // hart 2 again
    repeat (300) @(posedge clk);
    s2 = 0;
    `RAMPOKE(32'h550, 32'd1);
    waitfor(32'h558, 32'd3);
    repeat (200) @(posedge clk);
    for (i = 32'h540; i <= 32'h55f; i = i + 1)
      if (`RAMW(i) !== 32'd0) $display("W %0h %0h", i, `RAMW(i));
    $display("END %0d", cyc);
    $finish;
  end
endmodule
