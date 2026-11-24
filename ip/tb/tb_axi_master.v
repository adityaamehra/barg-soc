// Self-checking testbench for barg_axi_master with barg_dram behind it: random word writes (random byte strobes), word reads and line reads against a
// reference memory, plus an AXI protocol monitor (a valid stays until its ready and its payload stays the same; burst length, size, burst type,
// alignment, WLAST; no read and write activity at once; req_ready low while busy; one-cycle resp_valid; a response within a time limit).
// Prints "PASS" or "FAIL <what>". Parameters: BEATS_W, JITTER, READ_LAT, WRITE_LAT, SEED, N (requests). Written for Verilator.
module tb_axi_master;
  parameter integer BEATS_W = 3, JITTER = 0, READ_LAT = 3, WRITE_LAT = 2, ERR_EN = 0, ERR_IDX = 5, SEED = 1, N = 400;
  localparam integer LB = 1 << BEATS_W;
  localparam integer DEPTH_W = 8;

  reg clk = 0, rst = 1;
  reg req_valid = 0, req_we = 0, req_line = 0;
  reg [LB*32-1:0] req_wline = 0;
  reg [31:0] req_addr = 0, req_wdata = 0;
  reg [3:0] req_wstrb = 0;
  wire req_ready, resp_valid, resp_err;
  wire [LB*32-1:0] resp_data;
  wire arvalid, arready, rvalid, rready, rlast, awvalid, awready, wvalid, wready, wlast, bvalid, bready;
  wire [31:0] araddr, rdata, awaddr, wdata;
  wire [7:0] arlen, awlen;
  wire [2:0] arsize, awsize;
  wire [1:0] arburst, rresp, awburst, bresp;
  wire [3:0] wstrb;

  barg_axi_master #(.BEATS_W(BEATS_W)) m (
    .clk(clk), .rst(rst), .req_valid(req_valid), .req_ready(req_ready), .req_we(req_we), .req_line(req_line), .req_addr(req_addr), .req_wline(req_wline),
    .req_wdata(req_wdata), .req_wstrb(req_wstrb), .resp_valid(resp_valid), .resp_data(resp_data), .resp_err(resp_err),
    .m_axi_arvalid(arvalid), .m_axi_arready(arready), .m_axi_araddr(araddr), .m_axi_arlen(arlen), .m_axi_arsize(arsize), .m_axi_arburst(arburst),
    .m_axi_rvalid(rvalid), .m_axi_rready(rready), .m_axi_rdata(rdata), .m_axi_rresp(rresp), .m_axi_rlast(rlast),
    .m_axi_awvalid(awvalid), .m_axi_awready(awready), .m_axi_awaddr(awaddr), .m_axi_awlen(awlen), .m_axi_awsize(awsize), .m_axi_awburst(awburst),
    .m_axi_wvalid(wvalid), .m_axi_wready(wready), .m_axi_wdata(wdata), .m_axi_wstrb(wstrb), .m_axi_wlast(wlast),
    .m_axi_bvalid(bvalid), .m_axi_bready(bready), .m_axi_bresp(bresp));
  barg_dram #(.DEPTH_W(DEPTH_W), .READ_LAT(READ_LAT), .WRITE_LAT(WRITE_LAT), .JITTER(JITTER), .ERR_EN(ERR_EN), .ERR_IDX(ERR_IDX)) d (
    .clk(clk), .rst(rst),
    .s_axi_arvalid(arvalid), .s_axi_arready(arready), .s_axi_araddr(araddr), .s_axi_arlen(arlen), .s_axi_arsize(arsize), .s_axi_arburst(arburst),
    .s_axi_rvalid(rvalid), .s_axi_rready(rready), .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rlast(rlast),
    .s_axi_awvalid(awvalid), .s_axi_awready(awready), .s_axi_awaddr(awaddr), .s_axi_awlen(awlen), .s_axi_awsize(awsize), .s_axi_awburst(awburst),
    .s_axi_wvalid(wvalid), .s_axi_wready(wready), .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wlast(wlast),
    .s_axi_bvalid(bvalid), .s_axi_bready(bready), .s_axi_bresp(bresp));

  always #5 clk = ~clk;

  reg [31:0] refm [0:(1 << DEPTH_W) - 1];
  integer seed, errors, i, k, n, kind, waited, cyc;
  reg [31:0] a;
  reg exp_line, exp_we, busy, exp_err;

  task fail(input [8*48-1:0] what);
    begin
      $display("FAIL %0s (request %0d, cycle %0d)", what, n, cyc);
      errors = errors + 1;
      if (errors > 3) begin $display("FAIL too many errors"); $finish; end
    end
  endtask

  // protocol monitor
  reg p_arv = 0, p_arr = 0, p_awv = 0, p_awr = 0, p_wv = 0, p_wr = 0, p_rv = 0, p_rr = 0;
  reg [31:0] p_araddr = 0, p_awaddr = 0, p_wdata = 0, p_rdata = 0;
  reg [7:0] p_arlen = 0;
  reg [3:0] p_wstrb = 0;
  integer wbeat = 0;      // W beats accepted so far in the current request
  always @(posedge clk) if (!rst) begin
    cyc <= cyc + 1;
    if (p_arv && !p_arr && !(arvalid && araddr === p_araddr && arlen === p_arlen)) fail("AR changed or dropped before ARREADY");
    if (p_awv && !p_awr && !(awvalid && awaddr === p_awaddr)) fail("AW changed or dropped before AWREADY");
    if (p_wv && !p_wr && !(wvalid && wdata === p_wdata && wstrb === p_wstrb)) fail("W changed or dropped before WREADY");
    if (p_rv && !p_rr && !(rvalid && rdata === p_rdata)) fail("R changed or dropped before RREADY");
    if (arvalid) begin
      if (arsize !== 3'd2 || arburst !== 2'd1) fail("AR size or burst");
      if (arlen !== (exp_line ? LB - 1 : 0)) fail("AR length");
      if (araddr[1:0] !== 2'b00 || (exp_line && araddr[BEATS_W+1:0] !== 0)) fail("AR alignment");
      if (!busy || exp_we) fail("AR without a read request");
    end
    if (awvalid) begin
      if (awsize !== 3'd2 || awburst !== 2'd1 || awlen !== (exp_line ? LB - 1 : 0)) fail("AW size, burst or length");
      if (awaddr[1:0] !== 2'b00 || (exp_line && awaddr[BEATS_W+1:0] !== 0)) fail("AW alignment");
      if (!busy || !exp_we) fail("AW without a write request");
    end
    if (wvalid && wlast !== (wbeat == (exp_line ? LB - 1 : 0))) fail("WLAST");
    if (wvalid && exp_line && (wstrb !== 4'hF || wdata !== req_wline[wbeat*32 +: 32])) fail("line write beat");
    if (wvalid && wready) wbeat <= wbeat + 1;
    if (!busy) wbeat <= 0;
    if (wvalid && !exp_we) fail("W without a write request");
    if (resp_valid && !busy) fail("resp_valid with no request");
    p_arv <= arvalid; p_arr <= arready; p_araddr <= araddr; p_arlen <= arlen;
    p_awv <= awvalid; p_awr <= awready; p_awaddr <= awaddr;
    p_wv <= wvalid; p_wr <= wready; p_wdata <= wdata; p_wstrb <= wstrb;
    p_rv <= rvalid; p_rr <= rready; p_rdata <= rdata;
  end

  initial begin
    seed = SEED; errors = 0; cyc = 0; busy = 0; exp_line = 0; exp_we = 0; n = 0;
    for (i = 0; i < (1 << DEPTH_W); i = i + 1) refm[i] = 0;
    repeat (3) @(negedge clk);
    rst = 0;
    for (n = 0; n < N; n = n + 1) begin
      // wait for idle
      @(negedge clk);
      while (!req_ready) @(negedge clk);
      kind = ($random(seed) & 32'h7fffffff) % 10;
      a = $random(seed);
      a[31:DEPTH_W+2] = $random(seed);      // the memory ignores the high bits
      if (ERR_EN != 0 && (($random(seed) & 7) == 0)) a[DEPTH_W+1:2] = ERR_IDX + (($random(seed) & 3) - 1);   // often near the word that answers SLVERR
      req_addr = a;
      req_wdata = $random(seed);
      req_wstrb = $random(seed);
      req_we = (kind < 4);
      req_line = (!req_we && (kind >= 7)) || (req_we && kind == 3);     // kind 3: a line write
      for (k = 0; k < LB; k = k + 1) req_wline[k*32 +: 32] = $random(seed);
      exp_we = req_we; exp_line = req_line; busy = 1;
      req_valid = 1;
      @(negedge clk);
      req_valid = 0;
      // busy: not ready; wait for the one-cycle response
      waited = 0;
      while (!resp_valid && waited < 600) begin
        if (req_ready) fail("req_ready while busy");
        @(negedge clk); waited = waited + 1;
      end
      if (!resp_valid) begin fail("no response within the time limit"); $finish; end
      if (req_ready) fail("req_ready in the response cycle");
      i = a[DEPTH_W+1:2];
      if (req_we && req_line) exp_err = (ERR_EN != 0 && ERR_IDX >= (i & ~(LB - 1)) && ERR_IDX < (i & ~(LB - 1)) + LB);
      else if (req_we || !req_line) exp_err = (ERR_EN != 0 && i == ERR_IDX);
      else exp_err = (ERR_EN != 0 && ERR_IDX >= (i & ~(LB - 1)) && ERR_IDX < (i & ~(LB - 1)) + LB);
      if (resp_err !== exp_err) fail("resp_err wrong");
      if (req_we && req_line) begin
        i = i & ~(LB - 1);
        for (k = 0; k < LB; k = k + 1) if (!(ERR_EN != 0 && i + k == ERR_IDX)) refm[i + k] = req_wline[k*32 +: 32];
      end else if (req_we) begin
        if (!(ERR_EN != 0 && i == ERR_IDX)) for (k = 0; k < 4; k = k + 1) if (req_wstrb[k]) refm[i][8*k +: 8] = req_wdata[8*k +: 8];
      end else if (req_line) begin
        i = i & ~(LB - 1);
        for (k = 0; k < LB; k = k + 1) if (resp_data[k*32 +: 32] !== refm[i + k]) fail("line read data");
      end else begin
        if (resp_data[31:0] !== refm[i]) fail("word read data");
        if (LB > 1 && resp_data[LB*32-1:32] !== 0) fail("word read upper words not zero");
      end
      @(negedge clk);
      if (resp_valid) fail("resp_valid lasted more than one cycle");
      busy = 0;
    end
    if (errors == 0) $display("PASS"); else $display("FAIL %0d errors", errors);
    $finish;
  end
endmodule
