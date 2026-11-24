// Self-checking testbench for barg_uart. The reference is this file's own bit-level line model, written
// from the frame definition, not the DUT: a model transmitter drives rxd and a model receiver samples txd
// at mid-bit. Prints "PASS" or "FAIL <reason>" and finishes.
`timescale 1ns/1ps
module tb_uart;
  parameter integer CLK_DIV = 16, DATA_BITS = 8, PARITY = 0, STOP_BITS = 1, FIFO_AW = 2, N = 40, SEED = 1;
  localparam integer PB = (PARITY != 0) ? 1 : 0;
  localparam [DATA_BITS-1:0] MASK = {DATA_BITS{1'b1}};
  // Fewer random frames at slow bit rates (about two million clock cycles of them), never fewer than 8.
  localparam integer NB_CYC = CLK_DIV * (DATA_BITS + 4);
  localparam integer NN = (2000000 / NB_CYC) < 8 ? 8 : (2000000 / NB_CYC) > N ? N : (2000000 / NB_CYC);
  localparam integer DEPTH = 1 << FIFO_AW;
  reg clk = 0, rst = 1;
  always #5 clk = ~clk;
  reg  [DATA_BITS-1:0] tx_data = 0; reg tx_valid = 0; wire tx_ready;
  wire [DATA_BITS-1:0] rx_data; wire rx_valid; reg rx_ready = 0;
  wire rx_perr, rx_ferr, rx_overrun, txd; reg rxd = 1;
  barg_uart #(.CLK_DIV(CLK_DIV), .DATA_BITS(DATA_BITS), .PARITY(PARITY), .STOP_BITS(STOP_BITS), .FIFO_AW(FIFO_AW)) dut (
    .clk(clk), .rst(rst), .tx_data(tx_data), .tx_valid(tx_valid), .tx_ready(tx_ready),
    .rx_data(rx_data), .rx_valid(rx_valid), .rx_ready(rx_ready), .rx_parity_err(rx_perr), .rx_frame_err(rx_ferr),
    .rx_overrun(rx_overrun), .txd(txd), .rxd(rxd));

  integer seed = SEED, errors = 0;
  task fail(input [8*64-1:0] why); begin $display("FAIL %0s", why); errors = errors + 1; end endtask
  function par(input [DATA_BITS-1:0] d); par = (PARITY == 1) ? ~^d : ^d; endfunction

  // ---- model transmitter on rxd. Its bit period is CLK_DIV clocks times (1 + skew/1000), so a receiver that
  // does not sample near mid-bit fails; bad_par / bad_stop (a stop-bit number, 1-based; 0 = none) corrupt the frame.
  task send_line(input [DATA_BITS-1:0] d, input bad_par, input integer bad_stop, input integer skew);
    integer i; real bit_ns; begin
      bit_ns = 10.0 * CLK_DIV * (1000 + skew) / 1000.0;
      rxd = 0; #(bit_ns);
      for (i = 0; i < DATA_BITS; i = i + 1) begin rxd = d[i]; #(bit_ns); end
      if (PB) begin rxd = par(d) ^ bad_par; #(bit_ns); end
      for (i = 1; i <= STOP_BITS; i = i + 1) begin rxd = (bad_stop != i); #(bit_ns); end
      rxd = 1;
    end
  endtask
  // A low pulse shorter than a quarter bit: not a start bit, so it must not produce a frame.
  task glitch; begin rxd = 0; #(10 * (1 + ($random(seed) & 1) * (CLK_DIV / 4 - 1))); rxd = 1; end endtask

  // ---- model receiver on txd: waits for a start bit, samples every bit at its middle ----
  reg [DATA_BITS-1:0] tx_expect [0:NN]; integer tx_sent = 0, tx_seen = 0;
  initial begin : model_rx
    integer i; reg [DATA_BITS-1:0] d; reg p;
    forever begin
      @(negedge txd);
      #(CLK_DIV * 10 / 2);
      if (txd !== 1'b0) fail("tx start bit not low at mid-bit");
      for (i = 0; i < DATA_BITS; i = i + 1) begin #(CLK_DIV * 10); d[i] = txd; end
      if (PB) begin #(CLK_DIV * 10); p = txd; if (p !== par(d)) fail("tx parity bit wrong"); end
      for (i = 0; i < STOP_BITS; i = i + 1) begin #(CLK_DIV * 10); if (txd !== 1'b1) fail("tx stop bit not high"); end
      if (d !== tx_expect[tx_seen]) begin $display("FAIL tx frame %0d: got %h want %h", tx_seen, d, tx_expect[tx_seen]); errors = errors + 1; end
      tx_seen = tx_seen + 1;
    end
  end

  // ---- receive side expectations ----
  reg [DATA_BITS+1:0] rx_expect [0:NN + DEPTH]; integer rx_sent = 0, rx_seen = 0, overruns = 0;
  always @(posedge clk) begin
    if (rx_overrun) overruns <= overruns + 1;
    if (rx_valid && rx_ready) begin
      if ({rx_ferr, rx_perr, rx_data} !== rx_expect[rx_seen]) begin
        $display("FAIL rx frame %0d: got f%b p%b %h want %b", rx_seen, rx_ferr, rx_perr, rx_data, rx_expect[rx_seen]); errors = errors + 1;
      end
      rx_seen <= rx_seen + 1;
    end
  end

  integer k, ks, gap; reg [DATA_BITS-1:0] d, ds; reg bp;
  initial begin
    repeat (3) @(posedge clk); rst = 0;
    // Receive with random ready, random line gaps and corrupted frames, while the DUT transmits in parallel.
    fork
      begin : sender
        for (ks = 0; ks < NN; ks = ks + 1) begin
          ds = $random(seed) & MASK;
          @(posedge clk); tx_data <= ds; tx_valid <= 1; tx_expect[tx_sent] = ds; tx_sent = tx_sent + 1;
          @(posedge clk); while (!tx_ready) @(posedge clk);
          tx_valid <= 0;
          gap = $random(seed) & 7; repeat (gap) @(posedge clk);
        end
      end
      begin : line
        for (k = 0; k < NN; k = k + 1) begin : one
          integer g, bs, skew;
          d = $random(seed) & MASK; bp = PB && (($random(seed) & 7) == 0);
          bs = (($random(seed) & 7) == 0) ? 1 + (($random(seed) & 1) % STOP_BITS) : 0;
          skew = (k % 3 - 1) * 20;                        // -2%, 0, +2%
          rx_expect[rx_sent] = {bs != 0, bp, d}; rx_sent = rx_sent + 1;
          g = ($random(seed) & 3) * CLK_DIV / 3 + ($random(seed) & 3);
          repeat (g) @(posedge clk);
          if (($random(seed) & 3) == 0) begin glitch; repeat (CLK_DIV * 2) @(posedge clk); end
          // After a broken stop bit the line must be high for a while before the next start bit.
          send_line(d, bp, bs, skew); if (bs != 0) repeat (CLK_DIV) @(posedge clk);
        end
      end
      begin : reader
        while (rx_seen < NN) begin @(posedge clk); rx_ready <= ($random(seed) & 1); end
      end
    join
    rx_ready <= 0;
    // Overrun: with nobody reading, the FIFO fills, the next frame is dropped and rx_overrun pulses once.
    for (k = 0; k < DEPTH + 1; k = k + 1) begin
      d = k; if (k < DEPTH) begin rx_expect[rx_sent] = {2'b00, d}; rx_sent = rx_sent + 1; end
      send_line(d, 0, 0, 0); repeat (CLK_DIV) @(posedge clk);
    end
    if (overruns !== 1) begin $display("FAIL overrun pulses %0d, want 1", overruns); errors = errors + 1; end
    rx_ready <= 1; wait (rx_seen == rx_sent); @(posedge clk);
    wait (tx_seen == tx_sent);
    if (errors == 0) $display("PASS"); $finish;
  end
  initial begin #(64'd10 * NB_CYC * (3 * NN + 2 * DEPTH + 20) + 1000000); $display("FAIL timeout tx %0d/%0d rx %0d/%0d", tx_seen, tx_sent, rx_seen, rx_sent); $finish; end
endmodule
