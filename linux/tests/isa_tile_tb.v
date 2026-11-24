// Runs one riscv-test on the single-core tile. Plusargs: +HEX=<words file, word 0 at 0x8000_0000> +TOHOST=<hex address>
// +LIMIT=<cycles>. The program is loaded into the RAM before reset is released; the test ends when the word at tohost is written
// (1 is a pass; any other value is a failure, value>>1 is the failing check). Prints PASS or FAIL with the value and the cycles.
module isa_tile_tb;
  reg clk = 0, rst = 1;
  reg run = 1, grant = 1, ext_meip = 0, uart_rx_valid = 0;
  reg [1:0] hartid = 0;
  reg [63:0] mtime = 0;
  reg [31:0] plic_rdata = 0;
  reg [7:0] uart_rx_data = 0;
  wire req, ptw_req, uart_irq, uart_tx_valid, plic_we, plic_re;
  wire [7:0] uart_tx_data;
  reg [1023:0] hexfile;
  reg [31:0] tohost_addr;
  integer limit, cyc, done;
  reg [31:0] v;
  top dut (.clk(clk), .rst(rst), .run(run), .grant(grant), .hartid(hartid), .mtime(mtime),
           .ext_meip(ext_meip), .plic_rdata(plic_rdata), .uart_rx_valid(uart_rx_valid), .uart_rx_data(uart_rx_data),
           .req(req), .ptw_req(ptw_req), .uart_irq(uart_irq), .uart_tx_valid(uart_tx_valid), .uart_tx_data(uart_tx_data),
           .plic_we(plic_we), .plic_re(plic_re));
  always #5 clk = ~clk;
  initial begin
    if (!$value$plusargs("HEX=%s", hexfile)) begin $display("FAIL no HEX"); $finish; end
    if (!$value$plusargs("TOHOST=%h", tohost_addr)) tohost_addr = 32'h80001000;
    if (!$value$plusargs("LIMIT=%d", limit)) limit = 400000;
    #1;
    $readmemh(hexfile, dut.u_ram_main.u_ip.mem);
    repeat (3) @(posedge clk);
    rst <= 0;   // non-blocking: the core must still see reset at this edge
    done = 0;
    for (cyc = 0; cyc < limit && !done; cyc = cyc + 1) begin
      @(posedge clk);
      v = dut.u_ram_main.u_ip.mem[(tohost_addr - 32'h80000000) >> 2];
      if (v != 0) done = 1;
    end
    if (!done) $display("FAIL timeout after %0d cycles, tohost still 0", cyc);
    else if (v == 32'd1) $display("PASS in %0d cycles", cyc);
    else $display("FAIL tohost=%0d (check %0d) after %0d cycles", v, v >> 1, cyc);
    $finish;
  end
endmodule
