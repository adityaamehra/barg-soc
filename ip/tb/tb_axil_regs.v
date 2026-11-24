// Self-checking testbench for barg_axil_regs. A master model sends random writes and reads (address and data
// in random order and with random delays, random stalls on bready and rready), and a register model written
// from the bank's definition predicts every response, reg_q and every reg_wr pulse.
`timescale 1ns/1ps
module tb_axil_regs;
  parameter integer ADDR_W = 8, DATA_W = 32, N_RW = 4, N_RO = 0, N = 300, SEED = 1;
  localparam integer SB = $clog2(DATA_W / 8), NS = DATA_W / 8, RIW = N_RO > 0 ? N_RO * DATA_W : 1;
  localparam integer SPAN = (1 << (ADDR_W - SB)) < (N_RW + N_RO + 3) ? (1 << (ADDR_W - SB)) : (N_RW + N_RO + 3);
  reg clk = 0, rst = 1;
  always #5 clk = ~clk;
  reg [ADDR_W-1:0] awaddr = 0, araddr = 0; reg awvalid = 0, wvalid = 0, bready = 0, arvalid = 0, rready = 0;
  reg [DATA_W-1:0] wdata = 0; reg [NS-1:0] wstrb = 0;
  wire awready, wready, bvalid, arready, rvalid; wire [1:0] bresp, rresp; wire [DATA_W-1:0] rdata;
  wire [N_RW*DATA_W-1:0] reg_q; wire [N_RW-1:0] reg_wr; reg [RIW-1:0] reg_in;
  barg_axil_regs #(.ADDR_W(ADDR_W), .DATA_W(DATA_W), .N_RW(N_RW), .N_RO(N_RO)) dut (
    .clk(clk), .rst(rst),
    .s_axil_awaddr(awaddr), .s_axil_awprot(3'b000), .s_axil_awvalid(awvalid), .s_axil_awready(awready),
    .s_axil_wdata(wdata), .s_axil_wstrb(wstrb), .s_axil_wvalid(wvalid), .s_axil_wready(wready),
    .s_axil_bresp(bresp), .s_axil_bvalid(bvalid), .s_axil_bready(bready),
    .s_axil_araddr(araddr), .s_axil_arprot(3'b000), .s_axil_arvalid(arvalid), .s_axil_arready(arready),
    .s_axil_rdata(rdata), .s_axil_rresp(rresp), .s_axil_rvalid(rvalid), .s_axil_rready(rready),
    .reg_q(reg_q), .reg_wr(reg_wr), .reg_in(reg_in));

  integer seed = SEED, errors = 0, i, k;
  reg [DATA_W-1:0] model [0:N_RW-1];
  reg [N_RW-1:0] wr_seen;
  task fail(input [8*72-1:0] why); begin $display("FAIL %0s", why); errors = errors + 1; end endtask
  function [DATA_W-1:0] rnd; input dummy; reg [63:0] r; begin r = {$random(seed), $random(seed)}; rnd = r[DATA_W-1:0]; end endfunction

  always @(posedge clk) if (!rst) wr_seen <= wr_seen | reg_wr;
  // reg_q must equal the model at all times.
  always @(negedge clk) if (!rst) for (i = 0; i < N_RW; i = i + 1)
    if (reg_q[i*DATA_W +: DATA_W] !== model[i]) begin $display("FAIL reg_q[%0d] %h want %h", i, reg_q[i*DATA_W +: DATA_W], model[i]); errors = errors + 1; end

  task write(input integer idx, input [DATA_W-1:0] d, input [NS-1:0] s);
    integer da, dw, b; reg aw_done, w_done; reg [1:0] want;
    begin
      da = $random(seed) & 3; dw = $random(seed) & 3; aw_done = 0; w_done = 0;
      awaddr = (idx << SB) | ($random(seed) & ((1 << SB) - 1)); wdata = d; wstrb = s;
      wr_seen = 0;
      while (!(aw_done && w_done)) begin
        if (!aw_done && da == 0) awvalid = 1; if (!w_done && dw == 0) wvalid = 1;
        @(posedge clk);
        if (awvalid && awready) begin aw_done = 1; end
        if (wvalid && wready) begin w_done = 1; end
        #1; if (aw_done) awvalid = 0; if (w_done) wvalid = 0;
        if (da > 0) da = da - 1; if (dw > 0) dw = dw - 1;
      end
      want = (idx < N_RW) ? 2'b00 : 2'b10;
      // The write takes effect on the clock edge that raises bvalid, so the model changes there too.
      while (!bvalid) begin @(posedge clk); #1; end
      if (idx < N_RW) for (b = 0; b < NS; b = b + 1) if (s[b]) model[idx][b*8 +: 8] = d[b*8 +: 8];
      repeat ($random(seed) & 3) @(posedge clk);
      if (!bvalid) fail("bvalid dropped before bready");
      #1 bready = 1; @(posedge clk); #1 bready = 0;
      if (bresp !== want) begin $display("FAIL write %0d: bresp %b want %b", idx, bresp, want); errors = errors + 1; end
      @(posedge clk); #1;
      if (wr_seen !== ((idx < N_RW) ? ({{N_RW{1'b0}}, 1'b1} << idx) : {N_RW{1'b0}})) begin $display("FAIL write %0d: reg_wr pulses %b", idx, wr_seen); errors = errors + 1; end
    end
  endtask

  task read(input integer idx);
    reg [DATA_W-1:0] want; reg [1:0] wresp;
    begin
      araddr = (idx << SB) | ($random(seed) & ((1 << SB) - 1));
      repeat ($random(seed) & 3) @(posedge clk);
      #1 arvalid = 1; @(posedge clk); while (!arready) @(posedge clk); #1 arvalid = 0;
      while (!rvalid) @(posedge clk);
      repeat ($random(seed) & 3) @(posedge clk);
      if (idx < N_RW) begin want = model[idx]; wresp = 2'b00; end
      else if (idx < N_RW + N_RO) begin want = reg_in[(idx - N_RW) * DATA_W +: DATA_W]; wresp = 2'b00; end
      else begin want = 0; wresp = 2'b10; end
      if (!rvalid) fail("rvalid dropped before rready");
      if (rdata !== want || rresp !== wresp) begin $display("FAIL read %0d: %h/%b want %h/%b", idx, rdata, rresp, want, wresp); errors = errors + 1; end
      #1 rready = 1; @(posedge clk); #1 rready = 0;
    end
  endtask

  initial begin
    for (i = 0; i < N_RW; i = i + 1) model[i] = 0;
    for (i = 0; i < RIW; i = i + 32) reg_in[i +: 32] = $random(seed);
    repeat (3) @(posedge clk); #1 rst = 0;
    for (k = 0; k < N; k = k + 1) begin
      i = $unsigned($random(seed)) % SPAN;
      if ($random(seed) & 1) write(i, rnd(0), (($random(seed) & 3) == 0) ? $random(seed) : {NS{1'b1}});
      else read(i);
    end
    if (errors == 0) $display("PASS"); $finish;
  end
  initial begin #(64'd10 * N * 40 + 10000); $display("FAIL timeout"); $finish; end
endmodule
