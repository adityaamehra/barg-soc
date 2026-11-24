// Self-checking testbench for barg_i2c_master. The reference is an I2C slave model written from the protocol
// (START/STOP only with SCL high, bits sampled on SCL rising, ACK in the ninth clock, optional clock stretching,
// a second master for arbitration) plus checks on the wire: SCL high time, SDA setup and hold of at least
// CLK_DIV clocks, and the exact number of START and STOP conditions. Scenarios run in a fixed order until a
// cycle budget is used (a very slow SCL gets the first few only): write, read, repeated start, wrong address,
// data NACK, forced START and idle STOP, arbitration loss, then random transactions.
`timescale 1ns/1ps
module tb_i2c_master;
  parameter integer CLK_DIV = 3, STRETCH = 0, N = 40, SEED = 1;
  localparam [6:0] SADDR = 7'h50;
  localparam integer BYTE_CLK = 36 * CLK_DIV + 8;
  localparam integer BUDGET = 8000000;            // clock cycles
  reg clk = 0, rst = 1;
  always #5 clk = ~clk;
  reg cmd_valid = 0; wire cmd_ready; reg [1:0] cmd_op = 0; reg cmd_start = 0, cmd_stop = 0, cmd_nack = 0; reg [7:0] cmd_data = 0;
  wire rsp_valid, rsp_nack, rsp_arb_lost; wire [7:0] rsp_data; wire scl_o, sda_o;
  reg slv_scl = 1, slv_sda = 1, mst2 = 1;
  wire scl = scl_o & slv_scl;
  wire sda = sda_o & slv_sda & mst2;
  barg_i2c_master #(.CLK_DIV(CLK_DIV), .STRETCH(STRETCH)) dut (
    .clk(clk), .rst(rst), .cmd_valid(cmd_valid), .cmd_ready(cmd_ready), .cmd_op(cmd_op), .cmd_start(cmd_start),
    .cmd_stop(cmd_stop), .cmd_nack(cmd_nack), .cmd_data(cmd_data), .rsp_valid(rsp_valid), .rsp_data(rsp_data),
    .rsp_nack(rsp_nack), .rsp_arb_lost(rsp_arb_lost), .scl_o(scl_o), .scl_i(scl), .sda_o(sda_o), .sda_i(sda));

  integer seed = SEED, errors = 0;
  task fail(input [8*72-1:0] why); begin $display("FAIL %0s at %0t", why, $time); errors = errors + 1; end endtask

  // ---------------- slave model ----------------
  time t_start = 0;
  reg inframe = 0, mode = 0, first = 0, addr_ok = 0, ack_next = 0, mnack = 0, inj_nack = 0;
  integer bitn = 0, n_start = 0, n_stop = 0, nw = 0, nr = 0;
  reg [7:0] sbyte = 0, txb = 0;
  reg [7:0] wlog [0:1023]; reg [7:0] rsrc [0:1023];
  integer ii;
  initial for (ii = 0; ii < 1024; ii = ii + 1) rsrc[ii] = $random(seed);
  always @(negedge sda) if (scl === 1'b1 && !rst) begin n_start = n_start + 1; t_start = $time; inframe = 1; bitn = 0; mode = 0; first = 1; slv_sda = 1; end
  always @(posedge sda) if (scl === 1'b1 && !rst) begin n_stop = n_stop + 1; inframe = 0; mode = 0; slv_sda = 1; end
  always @(posedge scl) if (inframe) begin
    bitn = bitn + 1;
    if (!mode && bitn <= 8) sbyte = {sbyte[6:0], sda};
    if (!mode && bitn == 8) begin
      if (first) begin addr_ok = (sbyte[7:1] == SADDR); ack_next = addr_ok; end
      else begin ack_next = addr_ok && !inj_nack; if (ack_next) begin wlog[nw] = sbyte; nw = nw + 1; end end
    end
    if (mode && bitn == 9) begin mnack = sda; nr = nr + 1; end
  end
  always @(negedge scl) if (inframe) begin
    if (bitn == 8) slv_sda = mode ? 1'b1 : !ack_next;
    else if (bitn == 9) begin
      bitn = 0;
      if (!mode && first) begin
        first = 0;
        if (addr_ok && sbyte[0]) begin mode = 1; txb = rsrc[nr]; slv_sda = txb[7]; end else slv_sda = 1;
      end else if (mode) begin
        if (mnack) begin mode = 0; slv_sda = 1; end
        else begin txb = rsrc[nr]; slv_sda = txb[7]; end
      end else slv_sda = 1;
    end else if (mode && bitn >= 1 && bitn <= 7) slv_sda = txb[7 - bitn];
    if (STRETCH != 0 && ($random(seed) & 1)) begin
      slv_scl = 0; repeat (1 + ($unsigned($random(seed)) % (6 * CLK_DIV))) @(posedge clk); slv_scl = 1;
    end
  end

  // ---------------- wire checks ----------------
  time t_scl_rise = 0, t_scl_fall = 0, t_sda_o = 0; reg started = 0; reg arb_now = 0;
  always @(posedge scl) begin
    if (started && !arb_now && ($time - t_sda_o) < 10 * CLK_DIV && t_sda_o != 0) fail("scl rose less than CLK_DIV clocks after sda moved");
    t_scl_rise = $time; started = 1;
  end
  always @(negedge scl) if (started) begin
    if (!arb_now && t_start <= t_scl_rise) begin
      if (($time - t_scl_rise) < 20 * CLK_DIV) fail("scl high time below 2 x CLK_DIV clocks");
      if (STRETCH == 0 && ($time - t_scl_rise) != 20 * CLK_DIV) fail("scl high time is not 2 x CLK_DIV clocks");
      if (STRETCH != 0 && ($time - t_scl_rise) > 20 * CLK_DIV + 40) fail("scl high time too long with stretching");
    end
    t_scl_fall = $time;
  end
  always @(sda_o) if (started && !rst) begin
    if (!arb_now && ($time - t_scl_fall) < 10 * CLK_DIV && scl === 1'b0 && t_scl_fall > t_scl_rise) fail("sda moved less than CLK_DIV clocks after scl fell");
    if (!arb_now && scl === 1'b1 && ($time - t_scl_rise) < 10 * CLK_DIV) fail("sda moved less than CLK_DIV clocks after scl rose");
    t_sda_o = $time;
  end

  // ---------------- driver ----------------
  reg act = 0; integer exp_start = 0, exp_stop = 0; reg [7:0] r_data; reg r_nack, r_arb;
  task cmd(input [1:0] op, input st, input sp, input [7:0] d, input nk);
    begin
      @(posedge clk); #1; cmd_valid = 1; cmd_op = op; cmd_start = st; cmd_stop = sp; cmd_data = d; cmd_nack = nk;
      @(negedge clk); while (!cmd_ready) @(negedge clk);
      @(posedge clk); #1; cmd_valid = 0; cmd_data = 8'hxx;
      if (!op[1] && (st || !act)) begin exp_start = exp_start + 1; act = 1; end
      if (sp && (act || !op[1])) begin if (act) exp_stop = exp_stop + 1; act = 0; end
      @(negedge clk); while (!rsp_valid) @(negedge clk);
      r_data = rsp_data; r_nack = rsp_nack; r_arb = rsp_arb_lost;
      if (op[1] && (r_nack || r_arb)) fail("STOP-only response carries a flag");
      if (!act && !r_arb && (scl_o !== 1'b1 || sda_o !== 1'b1)) fail("bus not idle after STOP");
    end
  endtask
  task wr(input st, input sp, input [7:0] d, input want_nack);
    begin cmd(2'd0, st, sp, d, 0);
      if (r_arb) fail("unexpected arbitration loss");
      if (r_nack !== want_nack) begin $display("FAIL write %h: nack %b want %b", d, r_nack, want_nack); errors = errors + 1; end
      if (r_data !== d) begin $display("FAIL write %h: echo %h", d, r_data); errors = errors + 1; end
    end
  endtask
  reg [7:0] exp_wr [0:63]; integer n_exp_wr = 0, n_exp_rd = 0;
  task rd(input st, input sp, input nk);
    begin cmd(2'd1, st, sp, 8'h00, nk);
      if (r_data !== rsrc[n_exp_rd]) begin $display("FAIL read %0d: %h want %h", n_exp_rd, r_data, rsrc[n_exp_rd]); errors = errors + 1; end
      if (r_nack !== 1'b0) fail("rsp_nack set on a read");
      n_exp_rd = n_exp_rd + 1; end
  endtask
  task send_bytes(input integer k);    // k data bytes to SADDR, then STOP
    integer j; reg [63:0] r;
    begin wr(1, 0, {SADDR, 1'b0}, 0);
      for (j = 0; j < k; j = j + 1) begin r = {$random(seed), $random(seed)}; wlog_exp(r[7:0]); wr(0, j == k - 1, r[7:0], 0); end
    end
  endtask
  reg [7:0] wexp [0:1023]; integer nwe = 0;
  task wlog_exp(input [7:0] b); begin wexp[nwe] = b; nwe = nwe + 1; end endtask
  task read_bytes(input integer k);    // address with R, k data bytes, last one NACKed, STOP
    integer j;
    begin wr(1, 0, {SADDR, 1'b1}, 0);
      for (j = 0; j < k; j = j + 1) rd(0, j == k - 1, j == k - 1);
    end
  endtask
  reg [63:0] r; integer k, nb, kk;
  initial begin
    repeat (4) @(posedge clk); rst = 0; repeat (4) @(posedge clk);
    // 1. write, then read (the slave answers with its own stream)
    send_bytes(2); read_bytes(1);
    // 2. repeated START: write a pointer byte, then read two bytes
    if ($time < 10 * BUDGET / 4) begin
      wr(1, 0, {SADDR, 1'b0}, 0); wlog_exp(8'hA5); wr(0, 0, 8'hA5, 0);
      wr(1, 0, {SADDR, 1'b1}, 0); rd(0, 0, 0); rd(0, 1, 1);
    end
    // 3. wrong address: the byte is not acknowledged; STOP only closes the transaction
    if ($time < 10 * BUDGET / 2) begin
      wr(1, 0, {7'h51, 1'b0}, 1); cmd(2'd2, 0, 0, 0, 0);
      // 4. data NACK: the slave refuses the second data byte
      inj_nack = 0; wr(1, 0, {SADDR, 1'b0}, 0); wlog_exp(8'h3C); wr(0, 0, 8'h3C, 0);
      inj_nack = 1; wr(0, 1, 8'hC3, 1); inj_nack = 0;
    end
    // 5. a byte with no transaction open starts one; STOP only with nothing open does nothing
    if ($time < 10 * BUDGET / 2) begin
      cmd(2'd2, 0, 0, 0, 0);
      wr(0, 0, {SADDR, 1'b0}, 0); wlog_exp(8'h77); wr(0, 1, 8'h77, 0);
    end
    // 6. arbitration: a second master pulls SDA low while this one sends 1s
    if ($time < 10 * BUDGET / 2) begin
      fork
        begin : puller
          integer c; c = 0; arb_now = 0;
          repeat (6) begin @(negedge scl); c = c + 1; if (c == 4) begin mst2 = 0; arb_now = 1; end end
        end
        begin cmd(2'd0, 1, 1, 8'hFF, 0); end
      join_any
      @(posedge clk); wait (rsp_valid || r_arb); #1;
      if (!r_arb) fail("arbitration loss not reported");
      repeat (4) @(posedge clk);
      if (scl_o !== 1'b1 || sda_o !== 1'b1) fail("lines not released after arbitration loss");
      disable puller; mst2 = 1; act = 0; exp_stop = exp_stop + 1; arb_now = 0; repeat (8) @(posedge clk);
    end
    // 7. random transactions
    k = 0;
    while (k < N && $time < 10 * BUDGET) begin
      r = {$random(seed), $random(seed)}; nb = 1 + (r[3:0] % 4);
      if (r[4]) send_bytes(nb); else read_bytes(nb);
      k = k + 1;
    end
    repeat (6) @(posedge clk);
    if (n_start !== exp_start) begin $display("FAIL %0d START conditions on the wire, want %0d", n_start, exp_start); errors = errors + 1; end
    if (n_stop !== exp_stop) begin $display("FAIL %0d STOP conditions on the wire, want %0d", n_stop, exp_stop); errors = errors + 1; end
    for (kk = 0; kk < nwe && kk < nw; kk = kk + 1) if (wlog[kk] !== wexp[kk]) begin $display("FAIL slave stored byte %0d = %h want %h", kk, wlog[kk], wexp[kk]); errors = errors + 1; end
    if (nw != nwe) begin $display("FAIL slave stored %0d bytes, want %0d", nw, nwe); errors = errors + 1; end
    if (errors == 0) $display("PASS"); $finish;
  end
  initial begin #(64'd10 * (BUDGET + 40 * BYTE_CLK * 8) + 100000); $display("FAIL timeout"); $finish; end
endmodule
