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
// Boots an image (OpenSBI + Linux, a flat image for 0x8000_0000) on the quad-core SoC (the CPU-only build, --no-gpu). Every byte the
// UART transmits is printed as a character; a heartbeat line "[cycle N]" goes out every +BEAT cycles (default 5000000).
// Plusargs: +HEX=<words file, word 0 at 0x8000_0000>, +LIMIT=<cycles>, +BEAT=<cycles>, +RXFILE=<hex bytes to feed the UART receiver, one per line>
// +RXSTART=<cycle at which the first byte is sent>, +RXGAP=<cycles between bytes>.
module linux_quad_tb;
  reg clk = 0, rst = 1;
  reg meip = 0, rx_valid = 0, s2 = 0, s3 = 0;
  reg [7:0] rx_data = 0;
  wire uart_irq, uart_tx_valid, periph_we, periph_re;
  wire [7:0] uart_tx_data;
  wire [31:0] bus_addr, bus_wdata;
  integer limit, beat, cyc, rxstart, rxgap, rxn, rxi, traceat, tracelen, traptrace;
  reg prev_trap;
  reg [1023:0] hexfile, rxfile;
  reg [7:0] rxbuf [0:4095];
  reg have_rx;
  top dut (.clk(clk), .rst(rst), .rx_valid(rx_valid), .rx_data(rx_data), .ext_s2(s2), .ext_s3(s3), .meip(meip), `PPINS,
           .gpu_rdata(32'd0), .uart_irq(uart_irq), .uart_tx_valid(uart_tx_valid), .uart_tx_data(uart_tx_data),
           .periph_we(periph_we), .periph_re(periph_re), .bus_addr(bus_addr), .bus_wdata(bus_wdata));
  always #5 clk = ~clk;
  always @(posedge clk) if (uart_tx_valid) begin $write("%c", uart_tx_data); $fflush; end
  initial begin
    if (!$value$plusargs("HEX=%s", hexfile)) begin $display("no +HEX"); $finish; end
    if (!$value$plusargs("LIMIT=%d", limit)) limit = 100000000;
    if (!$value$plusargs("BEAT=%d", beat)) beat = 5000000;
    if (!$value$plusargs("RXSTART=%d", rxstart)) rxstart = 0;
    if (!$value$plusargs("RXGAP=%d", rxgap)) rxgap = 2000;
    if (!$value$plusargs("TRAPTRACE=%d", traptrace)) traptrace = 0;
    prev_trap = 0;
    if (!$value$plusargs("TRACEAT=%d", traceat)) traceat = -1;
    if (!$value$plusargs("TRACELEN=%d", tracelen)) tracelen = 400;
    have_rx = $value$plusargs("RXFILE=%s", rxfile);
    rxn = 0;
    if (!$value$plusargs("RXN=%d", rxn)) rxn = 0;   // the number of bytes in the file (Verilator is 2-state: no "x" marks the end)
    if (have_rx) $readmemh(rxfile, rxbuf);
    $readmemh(hexfile, dut.u_ram_main.u_ip.mem);
    repeat (3) @(posedge clk);
    rst <= 0;   // non-blocking: the core must still see reset at this edge
    rxi = 0;
    for (cyc = 0; cyc < limit; cyc = cyc + 1) begin
      @(posedge clk);
      rx_valid <= 0;
      // +TRAPTRACE=1: every trap hart 0 takes, "TRAP <e|i><cause> <epc> <tval> <m|s>", to compare with iss_s.py --trap-trace
      if (traptrace != 0) begin
        if ((dut.u_c0_trap_unit.trap_m || dut.u_c0_trap_unit.trap_s) && !prev_trap)
          $display("TRAP %s%0h %h %h %s", dut.u_c0_trap_unit.cause_val[31] ? "i" : "e", dut.u_c0_trap_unit.cause_val & 32'h7fffffff,
                   dut.u_c0_trap_unit.epc, dut.u_c0_trap_unit.tval_out, dut.u_c0_trap_unit.trap_s ? "s" : "m");
        prev_trap <= dut.u_c0_trap_unit.trap_m || dut.u_c0_trap_unit.trap_s;
      end
      if (traceat >= 0 && cyc >= traceat && cyc < traceat + tracelen)  // hart 0 program counter, one line per cycle, for diagnosis
        $display("T %0d pc %h  a4 %h a5 %h a0 %h  mtime %0d", cyc, dut.u_c0_pc.pc, dut.u_c0_regfile.mem[14], dut.u_c0_regfile.mem[15], dut.u_c0_regfile.mem[10], dut.u_clint4.mtime_reg);
      if (have_rx && rxi < rxn && cyc >= rxstart && ((cyc - rxstart) % rxgap) == 0) begin rx_valid <= 1; rx_data <= rxbuf[rxi]; rxi = rxi + 1; end
      if (cyc % beat == 0 && cyc != 0) begin
        $display("\n[cycle %0d  pc: hart0 %h hart1 %h hart2 %h hart3 %h]", cyc, dut.u_c0_pc.pc, dut.u_c1_pc.pc, dut.u_c2_pc.pc, dut.u_c3_pc.pc);
        $display("   hart0: ra %h sp %h a0 %h a1 %h  mtime %0d", dut.u_c0_regfile.mem[1], dut.u_c0_regfile.mem[2], dut.u_c0_regfile.mem[10], dut.u_c0_regfile.mem[11], dut.u_clint4.mtime_reg);
        $fflush;
      end
    end
    $display("\n[limit reached at cycle %0d]", cyc);
    $finish;
  end
endmodule
