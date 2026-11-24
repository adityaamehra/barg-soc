// Self-checking testbench for barg_spi_slave. The reference is a master model written from the SPI mode
// definition (CPOL/CPHA, bit order). It drives frames with random words and a random half-period of HP clocks
// (>= 4), then checks what the slave read (rx_data), what it sent (the master's own samples of miso), and the
// pulses: tx_load once per frame, rx_valid once per complete frame, rx_short for a cut frame, nothing for extra clocks.
`timescale 1ns/1ps
module tb_spi_slave;
  parameter integer DATA_W = 8, CPOL = 0, CPHA = 0, LSB_FIRST = 0, HP = 4, N = 40, SEED = 1;
  reg clk = 0, rst = 1;
  always #5 clk = ~clk;
  reg sclk = CPOL, cs_n = 1, mosi = 0; wire miso;
  reg [DATA_W-1:0] tx_data = 0; wire tx_load; wire [DATA_W-1:0] rx_data; wire rx_valid, rx_short;
  barg_spi_slave #(.DATA_W(DATA_W), .CPOL(CPOL), .CPHA(CPHA), .LSB_FIRST(LSB_FIRST)) dut (
    .clk(clk), .rst(rst), .sclk(sclk), .cs_n(cs_n), .mosi(mosi), .miso(miso),
    .tx_data(tx_data), .tx_load(tx_load), .rx_data(rx_data), .rx_valid(rx_valid), .rx_short(rx_short));

  integer seed = SEED, errors = 0, n_load = 0, n_valid = 0, n_short = 0;
  reg [DATA_W-1:0] last_rx;
  always @(posedge clk) begin
    if (tx_load) n_load <= n_load + 1;
    if (rx_valid) begin n_valid <= n_valid + 1; last_rx <= rx_data; end
    if (rx_short) n_short <= n_short + 1;
    if (rx_valid && rx_short) begin $display("FAIL rx_valid and rx_short together"); errors = errors + 1; end
  end
  function integer wire_bit(input integer i); wire_bit = LSB_FIRST ? i : DATA_W - 1 - i; endfunction
  // The master's pins change a random fraction of a clock after the clock edge, so they are asynchronous to clk.
  task jit; begin #(1 + $unsigned($random(seed)) % 19); end endtask
  task half; begin repeat (HP) @(posedge clk); end endtask

  // One frame: the master sends `mo`, expects the slave's word `so` back, makes `nclk` SCLK periods.
  reg [DATA_W-1:0] heard; integer i, lv_before, ld_before, sh_before;
  task frame(input [DATA_W-1:0] mo, input [DATA_W-1:0] so, input integer nclk);
    integer b; reg [DATA_W-1:0] h;
    begin
      h = 0; ld_before = n_load; lv_before = n_valid; sh_before = n_short;
      @(posedge clk); tx_data <= so; @(posedge clk); jit; cs_n = 0;
      if (CPHA == 0) mosi = mo[wire_bit(0)];
      half;                                   // the slave must have latched tx_data by now
      tx_data <= {DATA_W{1'bx}};
      for (b = 0; b < nclk; b = b + 1) begin
        if (CPHA == 0 && b < DATA_W) h[wire_bit(b)] = miso;      // CPHA 0 samples on the leading edge
        jit; sclk = ~CPOL;                                       // leading edge
        repeat (2) @(posedge clk);                               // the master changes mosi a little after its edge
        jit; if (CPHA == 1 && b < DATA_W) mosi = mo[wire_bit(b)];
        repeat (HP - 2) @(posedge clk);
        if (CPHA == 1 && b < DATA_W) h[wire_bit(b)] = miso;      // CPHA 1 samples on the trailing edge
        jit; sclk = CPOL;                                        // trailing edge
        repeat (2) @(posedge clk);
        jit; if (CPHA == 0 && b + 1 < DATA_W) mosi = mo[wire_bit(b+1)];
        repeat (HP - 2) @(posedge clk);
      end
      jit; cs_n = 1; repeat (8) @(posedge clk);
      heard = h;
      if (n_load != ld_before + 1) begin $display("FAIL tx_load pulsed %0d times in a frame", n_load - ld_before); errors = errors + 1; end
      if (nclk >= DATA_W) begin
        if (n_valid != lv_before + 1 || n_short != sh_before) begin $display("FAIL frame of %0d clocks: rx_valid %0d rx_short %0d", nclk, n_valid - lv_before, n_short - sh_before); errors = errors + 1; end
        if (last_rx !== mo) begin $display("FAIL slave read %h want %h", last_rx, mo); errors = errors + 1; end
        if (heard !== so) begin $display("FAIL master heard %h want %h", heard, so); errors = errors + 1; end
      end else if (nclk > 0) begin
        if (n_valid != lv_before || n_short != sh_before + 1) begin $display("FAIL cut frame (%0d of %0d): rx_valid %0d rx_short %0d", nclk, DATA_W, n_valid - lv_before, n_short - sh_before); errors = errors + 1; end
      end else if (n_valid != lv_before || n_short != sh_before) begin $display("FAIL empty frame produced a pulse"); errors = errors + 1; end
      repeat (HP) @(posedge clk);
    end
  endtask

  reg [63:0] r, s; integer k;
  initial begin
    repeat (4) @(posedge clk); rst = 0; repeat (4) @(posedge clk);
    for (k = 0; k < N; k = k + 1) begin
      r = {$random(seed), $random(seed)}; s = {$random(seed), $random(seed)};
      frame(r[DATA_W-1:0], s[DATA_W-1:0], DATA_W);
    end
    // Edge words
    frame({DATA_W{1'b1}}, {DATA_W{1'b0}}, DATA_W); frame({DATA_W{1'b0}}, {DATA_W{1'b1}}, DATA_W);
    // Extra clocks past DATA_W are ignored: still one rx_valid, same word
    r = {$random(seed), $random(seed)}; s = {$random(seed), $random(seed)};
    frame(r[DATA_W-1:0], s[DATA_W-1:0], DATA_W + 3);
    // A cut frame gives rx_short only, and the next frame is clean
    if (DATA_W > 1) begin frame(r[DATA_W-1:0], s[DATA_W-1:0], DATA_W - 1); frame(s[DATA_W-1:0], r[DATA_W-1:0], DATA_W); end
    frame(r[DATA_W-1:0], s[DATA_W-1:0], 0);
    if (errors == 0) $display("PASS"); $finish;
  end
  initial begin #(64'd10 * (N + 20) * (2 * DATA_W + 8) * (2 * HP + 12) + 100000); $display("FAIL timeout"); $finish; end
endmodule
