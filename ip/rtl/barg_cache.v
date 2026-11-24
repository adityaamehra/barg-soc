// barg_cache: the array of a set-associative cache (tags, data, valid, optional dirty, optional per-line state), without a controller. Written by
// rule from its parameters (no model writes it). The controller around it decides what to look up, when to fill, evict, invalidate and update.
//
// Geometry: 2^SET_W sets, WAYS ways, 2^LINE_W 32-bit words per line. A 32-bit byte address splits into
//   tag = addr[31 : 2+LINE_W+SET_W], set = addr[2+LINE_W+SET_W-1 : 2+LINE_W], word = addr[2+LINE_W-1 : 2], byte = addr[1:0] (ignored).
// All lookups are combinational from the held state and the inputs; all updates happen on the rising clock edge. Power-up: every line invalid,
// all data, tags and state zero. A synchronous reset invalidates every line and resets the replacement pointers; it does not clear data.
//
//  lookup (READ_PORTS ports; port p is bits p*32 +: 32 of lk_addr, and so on)
//    lk_hit      the line holding the address is present
//    lk_data     the addressed word of that line (0 when no hit)
//    lk_way      the way it is in (0 when no hit)
//    lk_state    the line's state field (0 when no hit); lk_dirty its dirty bit (0 when no hit or DIRTY is 0)
//  write hit (wr_en): when the line holding wr_addr is present, the bytes of its addressed word selected by wr_be take wr_data, and with DIRTY
//    the line becomes dirty; wr_hit says whether it was present (combinational, for the controller). A miss changes nothing.
//  fill (fill_en): installs the line of fill_addr with fill_data (word 0 in bits 31:0) and fill_state, valid and clean, in the way chosen by the
//    replacement rule: the lowest-numbered invalid way of the set, else the way the set's round-robin pointer names (the pointer then advances
//    by one, modulo WAYS; it is not advanced when an invalid way was used). Before the edge, vic_* describe the line that would be replaced:
//    vic_valid, vic_dirty, vic_addr (its line address, offset bits 0), vic_data, vic_state. Filling an address that is already present
//    installs a second copy: the controller must not do that.
//  invalidate: inv_en invalidates the line holding inv_addr (if present); inv_all invalidates every line.
//  state update (st_en): when the line holding st_addr is present, its state field becomes st_state, and with st_clean its dirty bit clears.
//  At most one of fill_en, inv_all, inv_en, st_en, wr_en per cycle; if several are set, the first in that order is done and the others are ignored.
module barg_cache #(
  parameter integer SET_W = 6,
  parameter integer WAYS = 2,
  parameter integer LINE_W = 3,
  parameter integer READ_PORTS = 1,
  parameter integer STATE_W = 0,
  parameter integer DIRTY = 0,
  // derived: do not override
  parameter integer SW = (STATE_W > 0) ? STATE_W : 1,
  parameter integer WW = (WAYS > 1) ? $clog2(WAYS) : 1,
  parameter integer LWORDS = (1 << LINE_W),
  parameter integer TAG_W = 30 - LINE_W - SET_W
) (
  input  wire                           clk,
  input  wire                           rst,
  input  wire [READ_PORTS*32-1:0]       lk_addr,
  output wire [READ_PORTS-1:0]          lk_hit,
  output wire [READ_PORTS*32-1:0]       lk_data,
  output wire [READ_PORTS*WW-1:0]       lk_way,
  output wire [READ_PORTS*SW-1:0]       lk_state,
  output wire [READ_PORTS-1:0]          lk_dirty,
  input  wire                           wr_en,
  input  wire [31:0]                    wr_addr,
  input  wire [31:0]                    wr_data,
  input  wire [3:0]                     wr_be,
  output wire                           wr_hit,
  input  wire                           fill_en,
  input  wire [31:0]                    fill_addr,
  input  wire [LWORDS*32-1:0]           fill_data,
  input  wire [SW-1:0]                  fill_state,
  output wire                           vic_valid,
  output wire                           vic_dirty,
  output wire [31:0]                    vic_addr,
  output wire [LWORDS*32-1:0]           vic_data,
  output wire [SW-1:0]                  vic_state,
  input  wire                           inv_en,
  input  wire [31:0]                    inv_addr,
  input  wire                           inv_all,
  input  wire                           st_en,
  input  wire [31:0]                    st_addr,
  input  wire [SW-1:0]                  st_state,
  input  wire                           st_clean
);
  localparam integer SETS = 1 << SET_W;
  localparam integer NLINES = SETS * WAYS;
  localparam integer IDX_LO = 2 + LINE_W;

  reg [TAG_W-1:0]      tag_q   [0:NLINES-1];
  reg [LWORDS*32-1:0]  data_q  [0:NLINES-1];
  reg [SW-1:0]         state_q [0:NLINES-1];
  reg [NLINES-1:0]     valid_q;
  reg [NLINES-1:0]     dirty_q;
  reg [WW-1:0]         ptr_q   [0:SETS-1];
  integer i;
  initial begin
    valid_q = {NLINES{1'b0}};
    dirty_q = {NLINES{1'b0}};
    for (i = 0; i < NLINES; i = i + 1) begin tag_q[i] = {TAG_W{1'b0}}; data_q[i] = {(LWORDS*32){1'b0}}; state_q[i] = {SW{1'b0}}; end
    for (i = 0; i < SETS; i = i + 1) ptr_q[i] = {WW{1'b0}};
  end

  // Where an address is: found says it is present, line is the index of its line (set * WAYS + way), way its way.
  // One finder per lookup port and one each for write, invalidate and state update (all combinational).
  // A finder is written once as a task-free block per instance through this generate.
  genvar g;
  generate for (g = 0; g < READ_PORTS; g = g + 1) begin : lk
    reg              found;
    reg [WW-1:0]     way;
    reg [31:0]       word;
    reg [SW-1:0]     stt;
    reg              dty;
    integer          w, line;
    reg [SET_W-1:0]  set;
    reg [LINE_W-1:0] off;
    reg [LWORDS*32-1:0] ln;
    always @* begin
      set = lk_addr[g*32 + IDX_LO +: SET_W];
      off = lk_addr[g*32 + 2 +: LINE_W];
      found = 1'b0; way = {WW{1'b0}}; stt = {SW{1'b0}}; dty = 1'b0; ln = {(LWORDS*32){1'b0}};
      for (w = 0; w < WAYS; w = w + 1) begin
        line = set * WAYS + w;
        if (!found && valid_q[line] && tag_q[line] == lk_addr[g*32 + 32 - TAG_W +: TAG_W]) begin
          found = 1'b1; way = w[WW-1:0]; stt = (STATE_W > 0) ? state_q[line] : {SW{1'b0}}; dty = dirty_q[line] & (DIRTY != 0); ln = data_q[line];
        end
      end
      word = found ? ln[off*32 +: 32] : 32'd0;
    end
    assign lk_hit[g] = found;
    assign lk_data[g*32 +: 32] = word;
    assign lk_way[g*WW +: WW] = way;
    assign lk_state[g*SW +: SW] = stt;
    assign lk_dirty[g] = dty;
  end endgenerate

  // finder for a single address (write, invalidate, state update)
  function automatic integer find_line(input [31:0] a);
    integer w, line, r;
    reg [SET_W-1:0] set;
    begin
      set = a[IDX_LO +: SET_W];
      r = -1;
      for (w = 0; w < WAYS; w = w + 1) begin
        line = set * WAYS + w;
        if (r < 0 && valid_q[line] && tag_q[line] == a[32 - TAG_W +: TAG_W]) r = line;
      end
      find_line = r;
    end
  endfunction

  integer wr_line, inv_line, st_line;
  always @* begin
    wr_line = find_line(wr_addr);
    inv_line = find_line(inv_addr);
    st_line = find_line(st_addr);
  end
  assign wr_hit = (wr_line >= 0);

  // victim of a fill at fill_addr
  reg [SET_W-1:0] fset;
  integer vic_line, vw, any_invalid;
  always @* begin
    fset = fill_addr[IDX_LO +: SET_W];
    any_invalid = 0;
    vic_line = fset * WAYS + ptr_q[fset];
    for (vw = WAYS - 1; vw >= 0; vw = vw - 1)
      if (!valid_q[fset * WAYS + vw]) begin any_invalid = 1; vic_line = fset * WAYS + vw; end
  end
  assign vic_valid = valid_q[vic_line];
  assign vic_dirty = dirty_q[vic_line] & (DIRTY != 0);
  assign vic_addr = {tag_q[vic_line], fset, {(LINE_W + 2){1'b0}}};
  assign vic_data = data_q[vic_line];
  assign vic_state = (STATE_W > 0) ? state_q[vic_line] : {SW{1'b0}};

  integer b;
  reg [LINE_W-1:0] woff;
  always @(posedge clk) begin
    if (rst) begin
      valid_q <= {NLINES{1'b0}};
      dirty_q <= {NLINES{1'b0}};
      for (i = 0; i < SETS; i = i + 1) ptr_q[i] <= {WW{1'b0}};
    end else if (fill_en) begin
      valid_q[vic_line] <= 1'b1;
      dirty_q[vic_line] <= 1'b0;
      tag_q[vic_line] <= fill_addr[32 - TAG_W +: TAG_W];
      data_q[vic_line] <= fill_data;
      state_q[vic_line] <= fill_state;
      if (!any_invalid) ptr_q[fset] <= (ptr_q[fset] == WAYS - 1) ? {WW{1'b0}} : ptr_q[fset] + 1'b1;
    end else if (inv_all) begin
      valid_q <= {NLINES{1'b0}};
    end else if (inv_en) begin
      if (inv_line >= 0) valid_q[inv_line] <= 1'b0;
    end else if (st_en) begin
      if (st_line >= 0) begin
        state_q[st_line] <= st_state;
        if (st_clean) dirty_q[st_line] <= 1'b0;
      end
    end else if (wr_en) begin
      if (wr_line >= 0) begin
        woff = wr_addr[2 +: LINE_W];
        for (b = 0; b < 4; b = b + 1)
          if (wr_be[b]) data_q[wr_line][woff*32 + b*8 +: 8] <= wr_data[b*8 +: 8];
        if (DIRTY != 0) dirty_q[wr_line] <= 1'b1;
      end
    end
  end
endmodule
