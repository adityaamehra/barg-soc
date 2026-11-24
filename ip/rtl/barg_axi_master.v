// barg_axi_master: an AXI4 master with a simple request port. One request at a time; 32-bit address and data.
//   word read   (req_we 0, req_line 0): one beat; resp_data bits 31:0 hold the word, the rest of resp_data is 0.
//   line read   (req_we 0, req_line 1): a burst of 2^BEATS_W beats from the line-aligned address (AXI INCR); resp_data holds the line, beat 0 in bits 31:0.
//   word write  (req_we 1, req_line 0): one beat with byte strobes req_wstrb at the word-aligned address.
//   line write  (req_we 1, req_line 1): a burst of 2^BEATS_W beats at the line-aligned address, beat j is bits 32*j+31:32*j of req_wline, all strobes 1.
// A request is taken in a cycle where req_valid and req_ready are both 1 (req_ready is 1 only when idle). resp_valid is 1 for exactly one cycle when
// the transaction is complete; resp_err is 1 in that cycle if any AXI response was not OKAY. Written by rule from its parameters (no model writes it).
// AXI: AxSIZE is 2 (4 bytes), AxBURST is 1 (INCR), a write is a single beat with WLAST 1. AWVALID and WVALID are raised together and each drops when
// accepted (a line write: AWVALID once, WVALID per beat, WLAST on the last). A synchronous active-high reset returns to idle.
module barg_axi_master #(
  parameter integer BEATS_W = 3,
  parameter integer LB = (1 << BEATS_W)      // derived: beats per line
) (
  input  wire                clk,
  input  wire                rst,
  input  wire                req_valid,
  output wire                req_ready,
  input  wire                req_we,
  input  wire                req_line,
  input  wire [31:0]         req_addr,
  input  wire [31:0]         req_wdata,
  input  wire [3:0]          req_wstrb,
  input  wire [LB*32-1:0]    req_wline,
  output wire                resp_valid,
  output wire [LB*32-1:0]    resp_data,
  output wire                resp_err,
  output wire                m_axi_arvalid,
  input  wire                m_axi_arready,
  output wire [31:0]         m_axi_araddr,
  output wire [7:0]          m_axi_arlen,
  output wire [2:0]          m_axi_arsize,
  output wire [1:0]          m_axi_arburst,
  input  wire                m_axi_rvalid,
  output wire                m_axi_rready,
  input  wire [31:0]         m_axi_rdata,
  input  wire [1:0]          m_axi_rresp,
  input  wire                m_axi_rlast,
  output wire                m_axi_awvalid,
  input  wire                m_axi_awready,
  output wire [31:0]         m_axi_awaddr,
  output wire [7:0]          m_axi_awlen,
  output wire [2:0]          m_axi_awsize,
  output wire [1:0]          m_axi_awburst,
  output wire                m_axi_wvalid,
  input  wire                m_axi_wready,
  output wire [31:0]         m_axi_wdata,
  output wire [3:0]          m_axi_wstrb,
  output wire                m_axi_wlast,
  input  wire                m_axi_bvalid,
  output wire                m_axi_bready,
  input  wire [1:0]          m_axi_bresp
);
  localparam [2:0] S_IDLE = 3'd0, S_AR = 3'd1, S_R = 3'd2, S_W = 3'd3, S_B = 3'd4, S_RESP = 3'd5;
  reg [2:0]          state;
  reg [31:0]         addr_q;
  reg                line_q;
  reg                wl_q;                   // a line write
  reg [31:0]         wdata_q;
  reg [3:0]          wstrb_q;
  reg [BEATS_W:0]    beat_q;
  reg [LB*32-1:0]    data_q;
  reg                err_q, aw_done, w_done;

  assign req_ready = (state == S_IDLE);
  assign resp_valid = (state == S_RESP);
  assign resp_data = data_q;
  assign resp_err = err_q;

  assign m_axi_arvalid = (state == S_AR);
  assign m_axi_araddr = addr_q;
  assign m_axi_arlen = line_q ? (LB - 1) : 8'd0;
  assign m_axi_arsize = 3'd2;
  assign m_axi_arburst = 2'd1;
  assign m_axi_rready = (state == S_R);
  assign m_axi_awvalid = (state == S_W) && !aw_done;
  assign m_axi_awaddr = addr_q;
  assign m_axi_awlen = wl_q ? (LB - 1) : 8'd0;
  assign m_axi_awsize = 3'd2;
  assign m_axi_awburst = 2'd1;
  assign m_axi_wvalid = (state == S_W) && !w_done;
  assign m_axi_wdata = wl_q ? data_q[beat_q*32 +: 32] : wdata_q;
  assign m_axi_wstrb = wl_q ? 4'hF : wstrb_q;
  assign m_axi_wlast = wl_q ? (beat_q == LB - 1) : 1'b1;
  assign m_axi_bready = (state == S_B);

  wire aw_now = aw_done || m_axi_awready;   // both channels done once each has been accepted (this cycle or before)
  wire w_now = w_done || (m_axi_wready && (!wl_q || beat_q == LB - 1));   // a line write is done with its last beat

  always @(posedge clk) begin
    if (rst) begin
      state <= S_IDLE; addr_q <= 32'd0; line_q <= 1'b0; wl_q <= 1'b0; wdata_q <= 32'd0; wstrb_q <= 4'd0; beat_q <= 0; data_q <= {(LB*32){1'b0}};
      err_q <= 1'b0; aw_done <= 1'b0; w_done <= 1'b0;
    end else begin
      case (state)
        S_IDLE: if (req_valid) begin
          line_q <= req_line & ~req_we;
          wl_q <= req_line & req_we;
          addr_q <= req_line ? (req_addr & ~((LB * 4) - 1)) : {req_addr[31:2], 2'b00};
          wdata_q <= req_wdata; wstrb_q <= req_wstrb;
          data_q <= (req_line & req_we) ? req_wline : {(LB*32){1'b0}}; err_q <= 1'b0; beat_q <= 0; aw_done <= 1'b0; w_done <= 1'b0;
          state <= req_we ? S_W : S_AR;
        end
        S_AR: if (m_axi_arready) state <= S_R;
        S_R: if (m_axi_rvalid) begin
          data_q[beat_q*32 +: 32] <= m_axi_rdata;
          if (m_axi_rresp != 2'b00) err_q <= 1'b1;
          if (m_axi_rlast) state <= S_RESP; else beat_q <= beat_q + 1'b1;
        end
        S_W: begin
          if (m_axi_awready) aw_done <= 1'b1;
          if (m_axi_wready && !w_done) begin
            if (wl_q && beat_q != LB - 1) beat_q <= beat_q + 1'b1; else w_done <= 1'b1;
          end
          if (aw_now && w_now) state <= S_B;
        end
        S_B: if (m_axi_bvalid) begin
          if (m_axi_bresp != 2'b00) err_q <= 1'b1;
          state <= S_RESP;
        end
        S_RESP: state <= S_IDLE;
        default: state <= S_IDLE;
      endcase
    end
  end
endmodule
