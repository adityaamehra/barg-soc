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
// Smoke test of the quad-core SoC (quad4): all four harts run the same program from reset.
// The program: x1 = mhartid + 0x10; x2 = mhartid << 2; x3 = 0x80000100 + x2; store x1 at 0(x3); spin.
// Expected: RAM word 0x40+k (address 0x80000100 + 4k) = k + 0x10 for k = 0..3. Prints PASS or FAIL.
module quad_smoke_tb;
  reg clk = 0, rst = 1;
  reg meip = 0, rx_valid = 0;
  reg [7:0] rx_data = 0;
  reg [31:0] plic_rdata = 0;
  wire uart_irq, uart_tx_valid, plic_we, plic_re;
  wire [7:0] uart_tx_data;
  integer i, cyc, k, bad;
  reg [31:0] prog [0:15];
  top dut (.clk(clk), .rst(rst), .rx_valid(rx_valid), .rx_data(rx_data), .ext_s2(1'b0), .ext_s3(1'b0), .meip(meip), `PPINS);
  always #5 clk = ~clk;
  initial begin
    for (i = 0; i < 16; i = i + 1) prog[i] = 32'h0000006F;
    prog[0] = 32'hF14020F3;  // csrr x1, mhartid
    prog[1] = 32'h00209113;  // slli x2, x1, 2
    prog[2] = 32'h800001B7;  // lui  x3, 0x80000
    prog[3] = 32'h10018193;  // addi x3, x3, 0x100
    prog[4] = 32'h002181B3;  // add  x3, x3, x2
    prog[5] = 32'h01008093;  // addi x1, x1, 0x10
    prog[6] = 32'h0011A023;  // sw   x1, 0(x3)
    prog[7] = 32'h0000006F;  // spin
    for (i = 0; i < 16; i = i + 1) dut.u_ram_main.u_ip.mem[i] = prog[i];
    repeat (3) @(posedge clk);
    rst <= 0;   // non-blocking: the core must still see reset at this edge
    for (cyc = 0; cyc < 4000; cyc = cyc + 1) @(posedge clk);
    bad = 0;
    for (k = 0; k < 4; k = k + 1)
      if (dut.u_ram_main.u_ip.mem[32'h40 + k] !== (k + 16)) begin
        bad = bad + 1;
        $display("word 0x%h = %h (want %h)", 32'h40 + k, dut.u_ram_main.u_ip.mem[32'h40 + k], k + 16);
      end
    if (bad == 0) $display("PASS four harts each stored their mhartid");
    else $display("FAIL %0d of 4 harts did not store their mhartid", bad);
    $finish;
  end
endmodule
