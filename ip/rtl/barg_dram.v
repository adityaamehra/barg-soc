// barg_dram: a behavioural external memory with an AXI4 slave port, for simulation (and as a small on-chip AXI memory). 2^DEPTH_W 32-bit words;
// the word index of an address is addr[DEPTH_W+1:2] (higher address bits are ignored, so the memory repeats through the address space). Power-up
// contents are zero; reset does not clear them. Written by rule from its parameters (no model writes it).
// AXI4 subset: 32-bit data, INCR bursts of any length (AxLEN + 1 beats, each beat the next word), byte strobes on writes. AxSIZE and AxBURST are not
// checked. Reads and writes are independent channels; one burst of each at a time.
//   READ_LAT   cycles from accepting a read address to the first read beat (0 = the beat is offered in the next cycle)
//   WRITE_LAT  cycles from accepting the last write beat to the write response
//   JITTER     0: fixed timing, ready signals always 1 when idle. 1: a 16-bit LFSR adds 0 to 3 cycles to each latency, delays each read beat by 0 to
//              3 cycles, and makes the address and write-data ready signals low in some cycles (for testing a master). A valid signal is never
//              withdrawn before its ready.
//   ERR_EN     1: the word with index ERR_IDX answers SLVERR (response 2): a read beat that returns it, and a write burst that touches it (the
//              write of that word is not done; the other words of the burst are). 0: every response is OKAY.
// A synchronous active-high reset returns both channels to idle.
module barg_dram #(
  parameter integer DEPTH_W = 16,
  parameter integer READ_LAT = 30,
  parameter integer WRITE_LAT = 4,
  parameter integer JITTER = 0,
  parameter integer ERR_EN = 0,
  parameter integer ERR_IDX = 0
) (
  input  wire        clk,
  input  wire        rst,
  input  wire        s_axi_arvalid,
  output wire        s_axi_arready,
  input  wire [31:0] s_axi_araddr,
  input  wire [7:0]  s_axi_arlen,
  input  wire [2:0]  s_axi_arsize,
  input  wire [1:0]  s_axi_arburst,
  output wire        s_axi_rvalid,
  input  wire        s_axi_rready,
  output wire [31:0] s_axi_rdata,
  output wire [1:0]  s_axi_rresp,
  output wire        s_axi_rlast,
  input  wire        s_axi_awvalid,
  output wire        s_axi_awready,
  input  wire [31:0] s_axi_awaddr,
  input  wire [7:0]  s_axi_awlen,
  input  wire [2:0]  s_axi_awsize,
  input  wire [1:0]  s_axi_awburst,
  input  wire        s_axi_wvalid,
  output wire        s_axi_wready,
  input  wire [31:0] s_axi_wdata,
  input  wire [3:0]  s_axi_wstrb,
  input  wire        s_axi_wlast,
  output wire        s_axi_bvalid,
  input  wire        s_axi_bready,
  output wire [1:0]  s_axi_bresp
);
  localparam integer DEPTH = 1 << DEPTH_W;
  reg [31:0] mem [0:DEPTH-1];
  integer j;
  initial for (j = 0; j < DEPTH; j = j + 1) mem[j] = 32'd0;

  reg [15:0] lfsr;
  wire [1:0] jit = (JITTER != 0) ? lfsr[1:0] : 2'd0;
  always @(posedge clk) begin
    if (rst) lfsr <= 16'hACE1;
    else lfsr <= {lfsr[14:0], lfsr[15] ^ lfsr[13] ^ lfsr[12] ^ lfsr[10]};
  end

  // ---------------------------------------------------------------- read channel
  localparam [1:0] R_IDLE = 2'd0, R_WAIT = 2'd1, R_BURST = 2'd2;
  reg [1:0]          r_state;
  reg [DEPTH_W-1:0]  r_idx;
  reg [7:0]          r_left;       // beats still to send, minus one
  reg [9:0]          r_cnt;
  reg [1:0]          r_gap;
  assign s_axi_arready = (r_state == R_IDLE) && ((JITTER == 0) || lfsr[3]);
  assign s_axi_rvalid = (r_state == R_BURST) && (r_gap == 2'd0);
  assign s_axi_rdata = mem[r_idx];
  assign s_axi_rresp = (ERR_EN != 0 && r_idx == ERR_IDX) ? 2'b10 : 2'b00;
  assign s_axi_rlast = (r_left == 8'd0);
  always @(posedge clk) begin
    if (rst) begin
      r_state <= R_IDLE; r_idx <= {DEPTH_W{1'b0}}; r_left <= 8'd0; r_cnt <= 10'd0; r_gap <= 2'd0;
    end else begin
      case (r_state)
        R_IDLE: if (s_axi_arvalid && s_axi_arready) begin
          r_idx <= s_axi_araddr[DEPTH_W+1:2]; r_left <= s_axi_arlen; r_gap <= 2'd0;
          if (READ_LAT + jit == 0) r_state <= R_BURST;
          else begin r_cnt <= READ_LAT + jit; r_state <= R_WAIT; end
        end
        R_WAIT: begin
          if (r_cnt <= 10'd1) r_state <= R_BURST;
          r_cnt <= r_cnt - 1'b1;
        end
        R_BURST: begin
          if (r_gap != 2'd0) r_gap <= r_gap - 1'b1;
          else if (s_axi_rready) begin
            r_idx <= r_idx + 1'b1;
            if (r_left == 8'd0) r_state <= R_IDLE;
            else begin r_left <= r_left - 1'b1; r_gap <= jit; end
          end
        end
        default: r_state <= R_IDLE;
      endcase
    end
  end

  // ---------------------------------------------------------------- write channel
  localparam [1:0] W_IDLE = 2'd0, W_DATA = 2'd1, W_DELAY = 2'd2, W_RESP = 2'd3;
  reg [1:0]          w_state;
  reg [DEPTH_W-1:0]  w_idx;
  reg [9:0]          w_cnt;
  assign s_axi_awready = (w_state == W_IDLE) && ((JITTER == 0) || lfsr[5]);
  assign s_axi_wready = (w_state == W_DATA) && ((JITTER == 0) || lfsr[7]);
  assign s_axi_bvalid = (w_state == W_RESP);
  reg w_err;
  assign s_axi_bresp = w_err ? 2'b10 : 2'b00;
  integer b;
  always @(posedge clk) begin
    if (rst) begin
      w_state <= W_IDLE; w_idx <= {DEPTH_W{1'b0}}; w_cnt <= 10'd0; w_err <= 1'b0;
    end else begin
      case (w_state)
        W_IDLE: if (s_axi_awvalid && s_axi_awready) begin
          w_idx <= s_axi_awaddr[DEPTH_W+1:2]; w_state <= W_DATA; w_err <= 1'b0;
        end
        W_DATA: if (s_axi_wvalid && s_axi_wready) begin
          if (ERR_EN != 0 && w_idx == ERR_IDX) w_err <= 1'b1;
          else for (b = 0; b < 4; b = b + 1) if (s_axi_wstrb[b]) mem[w_idx][8*b +: 8] <= s_axi_wdata[8*b +: 8];
          w_idx <= w_idx + 1'b1;
          if (s_axi_wlast) begin
            if (WRITE_LAT + jit == 0) w_state <= W_RESP;
            else begin w_cnt <= WRITE_LAT + jit; w_state <= W_DELAY; end
          end
        end
        W_DELAY: begin
          if (w_cnt <= 10'd1) w_state <= W_RESP;
          w_cnt <= w_cnt - 1'b1;
        end
        W_RESP: if (s_axi_bready) w_state <= W_IDLE;
        default: w_state <= W_IDLE;
      endcase
    end
  end
endmodule
