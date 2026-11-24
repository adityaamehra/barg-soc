// Self-checking testbench for barg_spi_master. The reference is a slave model written from the SPI mode
// definition (CPOL/CPHA, bit order), plus checks on the wire: SCLK idles at CPOL, each half period lasts
// CLK_DIV clocks, exactly the requested chip select is low, and it stays high CLK_DIV clocks between transfers.
`timescale 1ns/1ps
module tb_spi_master;
  parameter integer DATA_W = 8, CLK_DIV = 2, CPOL = 0, CPHA = 0, LSB_FIRST = 0, CS_W = 1, N = 30, SEED = 1;
  localparam integer SW = $clog2(CS_W > 1 ? CS_W : 2);
  // Fewer transfers at slow SCLK (about four million clock cycles of them), never fewer than 4.
  localparam integer T_CYC = 2 * DATA_W * CLK_DIV + 4 * CLK_DIV;
  localparam integer NN = (4000000 / T_CYC) < 4 ? 4 : (4000000 / T_CYC) > N ? N : (4000000 / T_CYC);
  reg clk = 0, rst = 1;
  always #5 clk = ~clk;
  reg [DATA_W-1:0] tx_data = 0; reg [SW-1:0] tx_cs = 0; reg tx_valid = 0; wire tx_ready;
  wire [DATA_W-1:0] rx_data; wire rx_valid; wire sclk, mosi; reg miso = 0; wire [CS_W-1:0] cs_n;
  barg_spi_master #(.DATA_W(DATA_W), .CLK_DIV(CLK_DIV), .CPOL(CPOL), .CPHA(CPHA), .LSB_FIRST(LSB_FIRST), .CS_W(CS_W)) dut (
    .clk(clk), .rst(rst), .tx_data(tx_data), .tx_cs(tx_cs), .tx_valid(tx_valid), .tx_ready(tx_ready),
    .rx_data(rx_data), .rx_valid(rx_valid), .sclk(sclk), .mosi(mosi), .miso(miso), .cs_n(cs_n));

  integer seed = SEED, errors = 0;
  task fail(input [8*72-1:0] why); begin $display("FAIL %0s", why); errors = errors + 1; end endtask

  // ---- expectations, one entry per transfer ----
  reg [DATA_W-1:0] want_mosi [0:NN]; reg [DATA_W-1:0] slave_word [0:NN]; reg [SW-1:0] want_cs [0:NN];
  integer started = 0, ended = 0, got = 0;

  // ---- slave model ----
  wire any_sel = ~&cs_n;
  integer bit_i; reg [DATA_W-1:0] heard; reg [CS_W-1:0] cs_want; reg nosel = 0; time last_edge; time cs_rise;
  function integer wire_bit(input integer i); wire_bit = LSB_FIRST ? i : DATA_W - 1 - i; endfunction
  always @(negedge (&cs_n)) begin   // some chip select fell
    if (($time - cs_rise) < 10 * CLK_DIV && ended > 0) fail("chip select high for less than CLK_DIV clocks");
    cs_want = ~({{CS_W{1'b0}}, 1'b1} << want_cs[ended]);
    if (cs_n !== cs_want) fail("wrong chip select");
    if (sclk !== CPOL[0]) fail("sclk not at CPOL when chip select fell");
    bit_i = 0; heard = 0; last_edge = $time;
    if (CPHA == 0) miso = slave_word[ended][wire_bit(0)];
  end
  always @(sclk) if (any_sel) begin : edge_model
    reg lead;
    if (($time - last_edge) != 10 * CLK_DIV) fail("sclk half period is not CLK_DIV clocks");
    last_edge = $time;
    lead = (sclk !== CPOL[0]);
    if ((CPHA == 0) == lead) begin                      // sampling edge
      if (bit_i < DATA_W) heard[wire_bit(bit_i)] = mosi;
      bit_i = bit_i + 1;
    end else begin                                      // shifting edge
      if (CPHA == 0) begin if (bit_i < DATA_W) miso = slave_word[ended][wire_bit(bit_i)]; end
      else if (bit_i < DATA_W) miso = slave_word[ended][wire_bit(bit_i)];
    end
  end else if (!rst && !nosel) fail("sclk moved with no chip select low");
  always @(posedge (&cs_n)) if (!rst) begin
    if (($time - last_edge) != 10 * CLK_DIV) fail("last edge to chip select rise is not CLK_DIV clocks");
    if (sclk !== CPOL[0]) fail("sclk not back at CPOL");
    if (bit_i != DATA_W) begin $display("FAIL transfer %0d: %0d sampling edges, want %0d", ended, bit_i, DATA_W); errors = errors + 1; end
    if (heard !== want_mosi[ended]) begin $display("FAIL transfer %0d: slave heard %h want %h", ended, heard, want_mosi[ended]); errors = errors + 1; end
    ended = ended + 1; cs_rise = $time;
  end
  always @(posedge clk) if (rx_valid && !nosel) begin
    if (rx_data !== slave_word[got]) begin $display("FAIL transfer %0d: master read %h want %h", got, rx_data, slave_word[got]); errors = errors + 1; end
    got <= got + 1;
  end

  integer k, gap; reg [63:0] r;
  initial begin
    cs_rise = 0;
    repeat (3) @(posedge clk); rst = 0;
    for (k = 0; k < NN; k = k + 1) begin
      r = {$random(seed), $random(seed)};
      want_mosi[k] = r[DATA_W-1:0]; r = {$random(seed), $random(seed)}; slave_word[k] = r[DATA_W-1:0];
      want_cs[k] = $unsigned($random(seed)) % CS_W;
      @(posedge clk); tx_data <= want_mosi[k]; tx_cs <= want_cs[k]; tx_valid <= 1;
      @(posedge clk); while (!tx_ready) @(posedge clk);
      tx_valid <= 0; tx_data <= {DATA_W{1'bx}};
      gap = $random(seed) & 3; repeat (gap) @(posedge clk);
    end
    wait (got == NN); repeat (2 * CLK_DIV + 2) @(posedge clk);
    if (ended != NN) begin $display("FAIL %0d transfers on the wire, want %0d", ended, NN); errors = errors + 1; end
    // A select value >= CS_W must select nobody, and the master must still finish and come back ready.
    if ((1 << SW) > CS_W) begin
      nosel = 1; @(posedge clk); tx_cs <= CS_W; tx_valid <= 1; @(posedge clk); tx_valid <= 0;
      repeat (2 * DATA_W * CLK_DIV + 4 * CLK_DIV + 4) @(posedge clk);
      if (!tx_ready || cs_n !== {CS_W{1'b1}}) fail("out-of-range select did not finish cleanly");
    end
    if (errors == 0) $display("PASS"); $finish;
  end
  initial begin #(64'd10 * (NN + 4) * (T_CYC + 8) + 100000); $display("FAIL timeout %0d/%0d", got, NN); $finish; end
endmodule
