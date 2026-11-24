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
// Generic testbench for the interrupt tests on the quad-core SoC. Plusargs (hex unless noted): +HEX=<image>, +DONE=<word index to
// watch>, +DONEVAL=<value that ends the run>, +EXTRA=<cycles to run after that (decimal)>, +LIMIT=<cycle limit (decimal)>,
// +LO=<first word index to print>, +HI=<last>. Prints "W <index> <value>" for every nonzero word in LO..HI, then "END <cycles>".
// Build with -DOLDTOP for the netlist without the PLIC pins.
module irq_dump_tb;
`include "memview.vh"
  reg clk = 0, rst = 1;
  reg meip = 0, rx_valid = 0, s2 = 0, s3 = 0;
  reg [7:0] rx_data = 0;
  wire uart_irq, uart_tx_valid;
  wire [7:0] uart_tx_data;
  integer cyc, limit, extra, i;
  reg [1023:0] hexfile;
  reg [31:0] done_idx, done_val, lo, hi;
`ifdef OLDTOP
  wire plic_we, plic_re;
  top dut (.clk(clk), .rst(rst), .rx_valid(rx_valid), .rx_data(rx_data), .plic_rdata(32'd0), .meip(meip),
           .uart_irq(uart_irq), .uart_tx_valid(uart_tx_valid), .uart_tx_data(uart_tx_data), .plic_we(plic_we), .plic_re(plic_re));
`else
  top dut (.clk(clk), .rst(rst), .rx_valid(rx_valid), .rx_data(rx_data), .ext_s2(s2), .ext_s3(s3), .meip(meip), `PPINS,
           .uart_irq(uart_irq), .uart_tx_valid(uart_tx_valid), .uart_tx_data(uart_tx_data));
`endif
  always #5 clk = ~clk;
  initial begin
    if (!$value$plusargs("HEX=%s", hexfile)) hexfile = "image.hex";
    if (!$value$plusargs("DONE=%h", done_idx)) done_idx = 0;
    if (!$value$plusargs("DONEVAL=%h", done_val)) done_val = 1;
    if (!$value$plusargs("EXTRA=%d", extra)) extra = 300;
    if (!$value$plusargs("LIMIT=%d", limit)) limit = 300000;
    if (!$value$plusargs("LO=%h", lo)) lo = 32'h400;
    if (!$value$plusargs("HI=%h", hi)) hi = 32'h5ff;
    $readmemh(hexfile, dut.u_ram_main.u_ip.mem);
    repeat (3) @(posedge clk);
    rst <= 0;   // non-blocking: the core must still see reset at this edge
    for (cyc = 0; cyc < limit && `RAMW(done_idx) !== done_val; cyc = cyc + 1) @(posedge clk);
    repeat (extra) @(posedge clk);
    for (i = lo; i <= hi; i = i + 1)
      if (`RAMW(i) !== 32'd0) $display("W %0h %0h", i, `RAMW(i));
    $display("END %0d", cyc);
    $finish;
  end
endmodule
