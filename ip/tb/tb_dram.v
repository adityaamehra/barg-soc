// Self-checking testbench for barg_dram alone: a behavioural AXI4 master issues random read bursts and write bursts (1 to 16 beats, random byte
// strobes) and compares every beat with a reference memory, and checks the slave side of the protocol (RLAST on the last beat only, read data stable while
// RVALID waits for RREADY, a response only after the last write beat, read and write channels used independently). Prints "PASS" or "FAIL <what>".
// Parameters: DEPTH_W, READ_LAT, WRITE_LAT, JITTER, SEED, N (bursts). Written for Verilator.
module tb_dram;
  parameter integer DEPTH_W = 8, READ_LAT = 3, WRITE_LAT = 2, JITTER = 0, ERR_EN = 0, ERR_IDX = 5, SEED = 1, N = 300;
  reg clk = 0, rst = 1;
  reg arvalid = 0, rready = 0, awvalid = 0, wvalid = 0, wlast = 0, bready = 0;
  reg [31:0] araddr = 0, awaddr = 0, wdata = 0;
  reg [7:0] arlen = 0, awlen = 0;
  reg [3:0] wstrb = 0;
  wire arready, rvalid, rlast, awready, wready, bvalid;
  wire [31:0] rdata;
  wire [1:0] rresp, bresp;
  barg_dram #(.DEPTH_W(DEPTH_W), .READ_LAT(READ_LAT), .WRITE_LAT(WRITE_LAT), .JITTER(JITTER), .ERR_EN(ERR_EN), .ERR_IDX(ERR_IDX)) d (
    .clk(clk), .rst(rst), .s_axi_arvalid(arvalid), .s_axi_arready(arready), .s_axi_araddr(araddr), .s_axi_arlen(arlen), .s_axi_arsize(3'd2),
    .s_axi_arburst(2'd1), .s_axi_rvalid(rvalid), .s_axi_rready(rready), .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rlast(rlast),
    .s_axi_awvalid(awvalid), .s_axi_awready(awready), .s_axi_awaddr(awaddr), .s_axi_awlen(awlen), .s_axi_awsize(3'd2), .s_axi_awburst(2'd1),
    .s_axi_wvalid(wvalid), .s_axi_wready(wready), .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wlast(wlast),
    .s_axi_bvalid(bvalid), .s_axi_bready(bready), .s_axi_bresp(bresp));
  always #5 clk = ~clk;

  reg [31:0] refm [0:(1 << DEPTH_W) - 1];
  integer seed, errors, i, n, beats, t, idx, guard, kind;
  reg [31:0] a;

  task fail(input [8*44-1:0] what);
    begin
      $display("FAIL %0s (burst %0d)", what, n);
      errors = errors + 1;
      if (errors > 3) begin $display("FAIL too many errors"); $finish; end
    end
  endtask

  // a read burst: address phase, then beats with random RREADY
  task read_burst(input [31:0] addr, input integer len);
    integer b, held;
    reg [31:0] prev;
    begin
      @(negedge clk); araddr = addr; arlen = len - 1; arvalid = 1;
      guard = 0;
      while (!(arvalid && arready)) begin @(negedge clk); guard = guard + 1; if (guard > 200) begin fail("no ARREADY"); $finish; end end
      // accepted at the coming edge
      @(negedge clk); arvalid = 0;
      for (b = 0; b < len; b = b + 1) begin
        held = 0; guard = 0;
        rready = (JITTER != 0) ? ($random(seed) & 1) : 1;
        while (!(rvalid && rready)) begin
          if (rvalid) begin
            if (held && rdata !== prev) fail("RDATA changed while waiting for RREADY");
            prev = rdata; held = 1;
          end
          @(negedge clk); guard = guard + 1;
          rready = (JITTER != 0) ? ($random(seed) & 1) : 1;
          if (guard > 400) begin fail("no read beat"); $finish; end
        end
        idx = ((addr[DEPTH_W+1:2]) + b) & ((1 << DEPTH_W) - 1);
        if (rdata !== refm[idx]) fail("read beat data");
        if (rlast !== (b == len - 1)) fail("RLAST");
        if (rresp !== ((ERR_EN != 0 && idx == ERR_IDX) ? 2'b10 : 2'b00)) fail("RRESP");
        @(negedge clk); rready = 0;
      end
    end
  endtask

  task write_burst(input [31:0] addr, input integer len);
    integer b, k2;
    reg werr;
    begin
      werr = 0;
      @(negedge clk); awaddr = addr; awlen = len - 1; awvalid = 1;
      guard = 0;
      while (!(awvalid && awready)) begin @(negedge clk); guard = guard + 1; if (guard > 200) begin fail("no AWREADY"); $finish; end end
      @(negedge clk); awvalid = 0;
      for (b = 0; b < len; b = b + 1) begin
        wdata = $random(seed); wstrb = $random(seed); wlast = (b == len - 1); wvalid = 1;
        guard = 0;
        while (!wready) begin @(negedge clk); guard = guard + 1; if (guard > 200) begin fail("no WREADY"); $finish; end end
        idx = ((addr[DEPTH_W+1:2]) + b) & ((1 << DEPTH_W) - 1);
        if (ERR_EN != 0 && idx == ERR_IDX) werr = 1;
        else for (k2 = 0; k2 < 4; k2 = k2 + 1) if (wstrb[k2]) refm[idx][8*k2 +: 8] = wdata[8*k2 +: 8];
        @(negedge clk); wvalid = 0; wlast = 0;
        if (bvalid && b != len - 1) fail("BVALID before the last write beat");
      end
      bready = (JITTER != 0) ? ($random(seed) & 1) : 1;
      guard = 0;
      while (!(bvalid && bready)) begin
        @(negedge clk); guard = guard + 1; bready = (JITTER != 0) ? ($random(seed) & 1) : 1;
        if (guard > 200) begin fail("no write response"); $finish; end
      end
      @(negedge clk); bready = 0;
      if (bresp !== (werr ? 2'b10 : 2'b00)) fail("BRESP");
    end
  endtask

  initial begin
    seed = SEED; errors = 0;
    for (i = 0; i < (1 << DEPTH_W); i = i + 1) refm[i] = 0;
    repeat (3) @(negedge clk);
    rst = 0;
    for (n = 0; n < N; n = n + 1) begin
      kind = ($random(seed) & 32'h7fffffff) % 5;
      beats = 1 + (($random(seed) & 32'h7fffffff) % 16);
      a = $random(seed);
      if (ERR_EN != 0 && (($random(seed) & 3) == 0)) a[DEPTH_W+1:2] = ERR_IDX - (($random(seed) & 7));   // bursts that run into the error word
      if (kind < 2) write_burst({a[31:2], 2'b00}, beats); else read_burst({a[31:2], 2'b00}, beats);
    end
    if (errors == 0) $display("PASS"); else $display("FAIL %0d errors", errors);
    $finish;
  end
endmodule
