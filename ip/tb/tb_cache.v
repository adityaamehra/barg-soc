// Self-checking testbench for barg_cache: random operations (lookups on every port every cycle; fills, write hits, invalidates, invalidate-all,
// state updates, several at once to check the priority) against a reference model written from the module's description. Every output is
// compared every cycle. Prints "PASS" or "FAIL <what>" and finishes. Parameters: the module's, SEED, N (cycles). Written for Verilator.
module tb_cache;
  parameter integer SET_W = 6, WAYS = 2, LINE_W = 3, READ_PORTS = 1, STATE_W = 0, DIRTY = 0, SEED = 1, N = 6000;
  localparam integer SW = (STATE_W > 0) ? STATE_W : 1;
  localparam integer WW = (WAYS > 1) ? $clog2(WAYS) : 1;
  localparam integer LWORDS = 1 << LINE_W;
  localparam integer TAG_W = 30 - LINE_W - SET_W;
  localparam integer SETS = 1 << SET_W;
  localparam integer NL = SETS * WAYS;
  localparam integer IDX_LO = 2 + LINE_W;

  reg clk = 0, rst = 1;
  reg [READ_PORTS*32-1:0] lk_addr = 0;
  wire [READ_PORTS-1:0] lk_hit, lk_dirty;
  wire [READ_PORTS*32-1:0] lk_data;
  wire [READ_PORTS*WW-1:0] lk_way;
  wire [READ_PORTS*SW-1:0] lk_state;
  reg wr_en = 0; reg [31:0] wr_addr = 0, wr_data = 0; reg [3:0] wr_be = 0; wire wr_hit;
  reg fill_en = 0; reg [31:0] fill_addr = 0; reg [LWORDS*32-1:0] fill_data = 0; reg [SW-1:0] fill_state = 0;
  wire vic_valid, vic_dirty; wire [31:0] vic_addr; wire [LWORDS*32-1:0] vic_data; wire [SW-1:0] vic_state;
  reg inv_en = 0, inv_all = 0; reg [31:0] inv_addr = 0;
  reg st_en = 0; reg [31:0] st_addr = 0; reg [SW-1:0] st_state = 0; reg st_clean = 0;

  barg_cache #(.SET_W(SET_W), .WAYS(WAYS), .LINE_W(LINE_W), .READ_PORTS(READ_PORTS), .STATE_W(STATE_W), .DIRTY(DIRTY)) dut (
    .clk(clk), .rst(rst), .lk_addr(lk_addr), .lk_hit(lk_hit), .lk_data(lk_data), .lk_way(lk_way), .lk_state(lk_state), .lk_dirty(lk_dirty),
    .wr_en(wr_en), .wr_addr(wr_addr), .wr_data(wr_data), .wr_be(wr_be), .wr_hit(wr_hit),
    .fill_en(fill_en), .fill_addr(fill_addr), .fill_data(fill_data), .fill_state(fill_state),
    .vic_valid(vic_valid), .vic_dirty(vic_dirty), .vic_addr(vic_addr), .vic_data(vic_data), .vic_state(vic_state),
    .inv_en(inv_en), .inv_addr(inv_addr), .inv_all(inv_all), .st_en(st_en), .st_addr(st_addr), .st_state(st_state), .st_clean(st_clean));

  always #5 clk = ~clk;

  // the reference model
  reg              mvalid [0:NL-1];
  reg              mdirty [0:NL-1];
  reg [TAG_W-1:0]  mtag   [0:NL-1];
  reg [31:0]       mdata  [0:NL*LWORDS-1];
  reg [SW-1:0]     mst    [0:NL-1];
  integer          mptr   [0:SETS-1];
  integer seed, cyc, errors, i, p, k, w;

  function integer mfind(input [31:0] a);
    integer ww, ln, r;
    reg [SET_W-1:0] s;
    begin
      s = a[IDX_LO +: SET_W];
      r = -1;
      for (ww = 0; ww < WAYS; ww = ww + 1) begin
        ln = s * WAYS + ww;
        if (r < 0 && mvalid[ln] && mtag[ln] == a[32 - TAG_W +: TAG_W]) r = ln;
      end
      mfind = r;
    end
  endfunction

  function [31:0] gen_addr(input integer dummy);
    integer t, s, wd, by, r;
    begin
      r = $random(seed);
      t = (r & 32'h7fffffff) % (2 * WAYS + 1);
      if (((r >> 16) & 15) == 0) t = $random(seed) & ((1 << (TAG_W > 20 ? 20 : TAG_W)) - 1);
      s = ($random(seed) & 32'h7fffffff) % ((SETS < 3) ? SETS : 3);
      if ((($random(seed) >> 8) & 15) == 0) s = $random(seed) & (SETS - 1);
      wd = $random(seed) & (LWORDS - 1);
      by = $random(seed) & 3;
      gen_addr = (t << (32 - TAG_W)) | (s << IDX_LO) | (wd << 2) | by;
    end
  endfunction

  task fail(input [8*40-1:0] what);
    begin
      $display("FAIL %0s at cycle %0d", what, cyc);
      errors = errors + 1;
      if (errors > 3) begin $display("FAIL too many errors"); $finish; end
    end
  endtask

  integer line, vl, any_inv, fs, ex_line, c1;
  reg [31:0] a;
  reg [LWORDS*32-1:0] exp_line;
  reg [31:0] exp_word;
  integer vic_ways_i;

  task check_outputs;
    begin
      for (p = 0; p < READ_PORTS; p = p + 1) begin
        a = lk_addr[p*32 +: 32];
        line = mfind(a);
        if (lk_hit[p] !== (line >= 0)) fail("lk_hit");
        else begin
          exp_word = (line >= 0) ? mdata[line * LWORDS + a[2 +: LINE_W]] : 32'd0;
          if (lk_data[p*32 +: 32] !== exp_word) fail("lk_data");
          if (lk_way[p*WW +: WW] !== ((line >= 0) ? (line % WAYS) : 0)) fail("lk_way");
          if (lk_state[p*SW +: SW] !== ((line >= 0 && STATE_W > 0) ? mst[line] : {SW{1'b0}})) fail("lk_state");
          if (lk_dirty[p] !== ((line >= 0 && DIRTY != 0) ? mdirty[line] : 1'b0)) fail("lk_dirty");
        end
      end
      if (wr_hit !== (mfind(wr_addr) >= 0)) fail("wr_hit");
      fs = fill_addr[IDX_LO +: SET_W];
      any_inv = 0; vl = fs * WAYS + mptr[fs];
      for (w = WAYS - 1; w >= 0; w = w - 1) if (!mvalid[fs * WAYS + w]) begin any_inv = 1; vl = fs * WAYS + w; end
      if (vic_valid !== mvalid[vl]) fail("vic_valid");
      if (vic_dirty !== ((DIRTY != 0) ? mdirty[vl] : 1'b0)) fail("vic_dirty");
      if (vic_addr !== ({mtag[vl], fs[SET_W-1:0], {(LINE_W + 2){1'b0}}})) fail("vic_addr");
      for (k = 0; k < LWORDS; k = k + 1) if (vic_data[k*32 +: 32] !== mdata[vl * LWORDS + k]) fail("vic_data");
      if (vic_state !== ((STATE_W > 0) ? mst[vl] : {SW{1'b0}})) fail("vic_state");
    end
  endtask

  task update_model;
    integer ul, bb;
    begin
      if (rst) begin
        for (i = 0; i < NL; i = i + 1) begin mvalid[i] = 0; mdirty[i] = 0; end
        for (i = 0; i < SETS; i = i + 1) mptr[i] = 0;
      end else if (fill_en) begin
        mvalid[vl] = 1; mdirty[vl] = 0; mtag[vl] = fill_addr[32 - TAG_W +: TAG_W];
        for (k = 0; k < LWORDS; k = k + 1) mdata[vl * LWORDS + k] = fill_data[k*32 +: 32];
        mst[vl] = (STATE_W > 0) ? fill_state : {SW{1'b0}};
        if (!any_inv) mptr[fs] = (mptr[fs] == WAYS - 1) ? 0 : mptr[fs] + 1;
      end else if (inv_all) begin
        for (i = 0; i < NL; i = i + 1) mvalid[i] = 0;
      end else if (inv_en) begin
        ul = mfind(inv_addr);
        if (ul >= 0) mvalid[ul] = 0;
      end else if (st_en) begin
        ul = mfind(st_addr);
        if (ul >= 0) begin
          mst[ul] = (STATE_W > 0) ? st_state : {SW{1'b0}};
          if (st_clean) mdirty[ul] = 0;
        end
      end else if (wr_en) begin
        ul = mfind(wr_addr);
        if (ul >= 0) begin
          for (bb = 0; bb < 4; bb = bb + 1)
            if (wr_be[bb]) mdata[ul * LWORDS + wr_addr[2 +: LINE_W]][bb*8 +: 8] = wr_data[bb*8 +: 8];
          if (DIRTY != 0) mdirty[ul] = 1;
        end
      end
    end
  endtask

  integer r;
  initial begin
    seed = SEED; errors = 0;
    for (i = 0; i < NL; i = i + 1) begin
      mvalid[i] = 0; mdirty[i] = 0; mtag[i] = 0; mst[i] = 0;
      for (k = 0; k < LWORDS; k = k + 1) mdata[i * LWORDS + k] = 0;
    end
    for (i = 0; i < SETS; i = i + 1) mptr[i] = 0;
    // reset for two cycles
    @(negedge clk); rst = 1; @(negedge clk); #1; check_outputs; @(posedge clk); update_model; @(negedge clk); rst = 0;
    for (cyc = 0; cyc < N; cyc = cyc + 1) begin
      for (p = 0; p < READ_PORTS; p = p + 1) lk_addr[p*32 +: 32] = gen_addr(0);
      wr_addr = gen_addr(0); wr_data = $random(seed); wr_be = $random(seed);
      inv_addr = gen_addr(0); st_addr = gen_addr(0); st_state = $random(seed); st_clean = $random(seed);
      fill_addr = gen_addr(0); fill_state = $random(seed);
      for (k = 0; k < LWORDS; k = k + 1) fill_data[k*32 +: 32] = $random(seed);
      r = $random(seed) & 255;
      fill_en = (r < 40) && (mfind(fill_addr) < 0);   // a controller never fills an address that is present
      wr_en = (($random(seed) & 255) < 100);
      inv_en = (($random(seed) & 255) < 20);
      st_en = (($random(seed) & 255) < 25);
      inv_all = (($random(seed) & 255) < 2);
      if (($random(seed) & 3) != 0) begin             // mostly one operation at a time
        r = ($random(seed) & 32'h7fffffff) % 5;
        fill_en = fill_en & (r == 0); wr_en = wr_en & (r == 1); inv_en = inv_en & (r == 2); st_en = st_en & (r == 3); inv_all = inv_all & (r == 4);
      end
      #1;
      check_outputs;
      @(posedge clk);
      update_model;
      @(negedge clk);
    end
    if (errors == 0) $display("PASS"); else $display("FAIL %0d errors", errors);
    $finish;
  end
endmodule
