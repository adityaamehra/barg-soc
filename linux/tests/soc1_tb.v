// Smoke test of the single-core tile (soc1): a short program in the RAM, run from reset.
// The program: x1=5; x2=7; x3=x1+x2; store x3 at 0x80000100; load it back to x5; x6=x5+x1; store x6 at 0x80000104; spin.
// Expected: RAM word 0x40 (address 0x80000100) = 12, RAM word 0x41 (address 0x80000104) = 17. Prints PASS or FAIL.
module soc1_tb;
  reg clk = 0, rst = 1;
  reg run = 1, grant = 1, ext_meip = 0, uart_rx_valid = 0;
  reg [1:0] hartid = 0;
  reg [63:0] mtime = 0;
  reg [31:0] plic_rdata = 0;
  reg [7:0] uart_rx_data = 0;
  wire req, ptw_req, uart_irq, uart_tx_valid, plic_we, plic_re;
  wire [7:0] uart_tx_data;
  integer i, cyc;
  reg [31:0] prog [0:15];
  top dut (.clk(clk), .rst(rst), .run(run), .grant(grant), .hartid(hartid), .mtime(mtime),
           .ext_meip(ext_meip), .plic_rdata(plic_rdata), .uart_rx_valid(uart_rx_valid), .uart_rx_data(uart_rx_data),
           .req(req), .ptw_req(ptw_req), .uart_irq(uart_irq), .uart_tx_valid(uart_tx_valid), .uart_tx_data(uart_tx_data),
           .plic_we(plic_we), .plic_re(plic_re));
  always #5 clk = ~clk;
  initial begin
    for (i = 0; i < 16; i = i + 1) prog[i] = 32'h0000006F;
    prog[0] = 32'h00500093;  // addi x1, x0, 5
    prog[1] = 32'h00700113;  // addi x2, x0, 7
    prog[2] = 32'h002081B3;  // add  x3, x1, x2
    prog[3] = 32'h80000237;  // lui  x4, 0x80000
    prog[4] = 32'h10020213;  // addi x4, x4, 0x100
    prog[5] = 32'h00322023;  // sw   x3, 0(x4)
    prog[6] = 32'h00022283;  // lw   x5, 0(x4)
    prog[7] = 32'h00128333;  // add  x6, x5, x1
    prog[8] = 32'h00622223;  // sw   x6, 4(x4)
    prog[9] = 32'h0000006F;  // spin
    for (i = 0; i < 16; i = i + 1) dut.u_ram_main.u_ip.mem[i] = prog[i];
    repeat (3) @(posedge clk);
    rst <= 0;   // non-blocking: the core must still see reset at this edge
    for (cyc = 0; cyc < 400; cyc = cyc + 1) @(posedge clk);
    if (dut.u_ram_main.u_ip.mem[32'h40] === 32'd12 && dut.u_ram_main.u_ip.mem[32'h41] === 32'd17) $display("PASS store 12, load, add 17, store 17");
    else $display("FAIL word 0x40=%h (want 0000000c) word 0x41=%h (want 00000011)", dut.u_ram_main.u_ip.mem[32'h40], dut.u_ram_main.u_ip.mem[32'h41]);
    $finish;
  end
endmodule
