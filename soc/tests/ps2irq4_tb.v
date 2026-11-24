`ifdef PS2
`include "ps2_device.vh"
`endif
`ifdef PERIPH
`define PPINS .gpio_in(16'd0), .spi_miso(1'b0), .i2c_scl_i(1'b1), .i2c_sda_i(1'b1)
`else
`define PPINS .periph_rdata(32'd0)
`endif
// Drives ps2irq4.S on the quad-core SoC with a PS/2 keyboard and a PS/2 mouse model (ps2_device.vh) on the two ports. When the program says the mouse
// is enabled (word 0x588) the mouse sends a three-byte packet; when it says the keyboard interrupt is enabled (word 0x589) the keyboard sends a key.
// Prints the nonzero words 0x580..0x59f ("W <index> <value>") and END.
module ps2irq4_tb;
`include "memview.vh"
  reg clk = 0, rst = 1;
  reg meip = 0, rx_valid = 0, s2 = 0, s3 = 0;
  reg [7:0] rx_data = 0;
  wire uart_irq, uart_tx_valid;
  wire [7:0] uart_tx_data;
  integer cyc, limit, i;
  reg [1023:0] hexfile;
  wire ps2k_clk_low, ps2k_dat_low, ps2m_clk_low, ps2m_dat_low, ps2k_clk_i, ps2k_dat_i, ps2m_clk_i, ps2m_dat_i;
  ps2_device #(.MOUSE(0)) u_kbd (.clk(clk), .rst(rst), .host_clk_low(ps2k_clk_low), .host_dat_low(ps2k_dat_low), .clk_line(ps2k_clk_i), .dat_line(ps2k_dat_i));
  ps2_device #(.MOUSE(1)) u_mouse (.clk(clk), .rst(rst), .host_clk_low(ps2m_clk_low), .host_dat_low(ps2m_dat_low), .clk_line(ps2m_clk_i), .dat_line(ps2m_dat_i));
  top dut (.clk(clk), .rst(rst), .rx_valid(rx_valid), .rx_data(rx_data), .ext_s2(s2), .ext_s3(s3), .meip(meip), `PPINS,
           .ps2k_clk_i(ps2k_clk_i), .ps2k_dat_i(ps2k_dat_i), .ps2k_clk_low(ps2k_clk_low), .ps2k_dat_low(ps2k_dat_low),
           .ps2m_clk_i(ps2m_clk_i), .ps2m_dat_i(ps2m_dat_i), .ps2m_clk_low(ps2m_clk_low), .ps2m_dat_low(ps2m_dat_low),
           .uart_irq(uart_irq), .uart_tx_valid(uart_tx_valid), .uart_tx_data(uart_tx_data));
  always #5 clk = ~clk;
  reg dbg = 0;
  initial dbg = $test$plusargs("DBG");
  integer dc = 0;
  always @(posedge clk) begin
    dc <= dc + 1;
    if (dbg && (dc % 25000) == 0) begin
      $display("DBG dc=%0d dclk=%b ddat=%b hcl=%b hdl=%b inh=%0d rb=%h bits=%b rx_cnt=%0d rx_sh=%b rx_cmds=%0d sent=%0d q=%0d..%0d tx_st=%0d fifo=%0d pc=%h", dc, u_kbd.dclk, u_kbd.ddat, ps2k_clk_low, ps2k_dat_low, u_kbd.inh, u_kbd.rb, u_kbd.bits, dut.u_ps2k_rx.cnt, dut.u_ps2k_rx.sh,
               u_kbd.nrx_cmds, u_kbd.nbytes_sent, u_kbd.qh, u_kbd.qt, dut.u_ps2k_tx.st, dut.u_ps2k_fifo.count, dut.u_c0_pc.pc);
    end
  end
  task waitfor(input [31:0] idx, input [31:0] val);
    begin
      while (cyc < limit && `RAMW(idx) !== val) begin @(posedge clk); cyc = cyc + 1; end
    end
  endtask
  initial begin
    if (!$value$plusargs("HEX=%s", hexfile)) hexfile = "image.hex";
    if (!$value$plusargs("LIMIT=%d", limit)) limit = 4000000;
    $readmemh(hexfile, dut.u_ram_main.u_ip.mem);
    cyc = 0;
    repeat (3) @(posedge clk);
    rst <= 0;
    waitfor(32'h588, 32'd1);
    u_mouse.push_ext(8'h09); u_mouse.push_ext(8'h05); u_mouse.push_ext(8'hFB);
    waitfor(32'h589, 32'd1);
    for (i = 0; i < 24; i = i + 1) u_kbd.push_ext(8'h40 + i[7:0]);   // a burst of 24 bytes, like a fast typist's make and break codes
    waitfor(32'h59F, 32'h600D);
    repeat (200) @(posedge clk);
    for (i = 32'h580; i <= 32'h5df; i = i + 1)
      if (`RAMW(i) !== 32'd0) $display("W %0h %0h", i, `RAMW(i));
    $display("END %0d", cyc);
    $finish;
  end
endmodule
