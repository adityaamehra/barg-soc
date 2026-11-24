// AXI4-Lite slave register bank. Hand-written curated IP; no part is generated.
//
// Parameters
//   ADDR_W  >= log2(bytes in the bank), <= 32   address bits
//   DATA_W  32, 64                              register and bus width
//   N_RW    1..64                               read-write registers, at word addresses 0 .. N_RW-1; reset to 0
//   N_RO    0..64                               read-only registers after them, read from reg_in
//
// Word index = address / (DATA_W/8); the low address bits are ignored. A write applies the byte strobes and pulses
// reg_wr for one cycle. A write to a read-only register or past the bank, or a read past it, is answered SLVERR
// and changes nothing. One write and one read may be outstanding at a time. Reset is synchronous and active high.
// reg_q holds register 0 in its low DATA_W bits; reg_in likewise. When N_RO = 0, reg_in is one unused bit.
module barg_axil_regs #(
  parameter integer ADDR_W = 8,
  parameter integer DATA_W = 32,
  parameter integer N_RW   = 4,
  parameter integer N_RO   = 0
) (
  input  wire                                         clk,
  input  wire                                         rst,
  input  wire [ADDR_W-1:0]                            s_axil_awaddr,
  input  wire [2:0]                                   s_axil_awprot,
  input  wire                                         s_axil_awvalid,
  output wire                                         s_axil_awready,
  input  wire [DATA_W-1:0]                            s_axil_wdata,
  input  wire [DATA_W/8-1:0]                          s_axil_wstrb,
  input  wire                                         s_axil_wvalid,
  output wire                                         s_axil_wready,
  output reg  [1:0]                                   s_axil_bresp,
  output reg                                          s_axil_bvalid,
  input  wire                                         s_axil_bready,
  input  wire [ADDR_W-1:0]                            s_axil_araddr,
  input  wire [2:0]                                   s_axil_arprot,
  input  wire                                         s_axil_arvalid,
  output wire                                         s_axil_arready,
  output reg  [DATA_W-1:0]                            s_axil_rdata,
  output reg  [1:0]                                   s_axil_rresp,
  output reg                                          s_axil_rvalid,
  input  wire                                         s_axil_rready,
  output wire [N_RW*DATA_W-1:0]                       reg_q,
  output reg  [N_RW-1:0]                              reg_wr,
  input  wire [(N_RO > 0 ? N_RO * DATA_W : 1)-1:0]    reg_in
);
  localparam integer SB = $clog2(DATA_W / 8);            // byte-offset bits
  localparam integer IW = ADDR_W - SB;                   // word-index bits
  localparam [1:0] OKAY = 2'b00, SLVERR = 2'b10;

  reg [DATA_W-1:0] regs [0:N_RW-1];
  genvar g;
  generate for (g = 0; g < N_RW; g = g + 1) begin : g_q
    assign reg_q[g*DATA_W +: DATA_W] = regs[g];
  end endgenerate

  // ---- write: address and data may come in either order; the response goes out when both are in ----
  reg              aw_have, w_have;
  reg [IW-1:0]     aw_idx;
  reg [DATA_W-1:0] w_data;
  reg [DATA_W/8-1:0] w_strb;
  assign s_axil_awready = !aw_have && !s_axil_bvalid;
  assign s_axil_wready  = !w_have && !s_axil_bvalid;
  integer i, b;
  always @(posedge clk) begin
    reg_wr <= {N_RW{1'b0}};
    if (rst) begin
      aw_have <= 1'b0; w_have <= 1'b0; aw_idx <= 0; w_data <= 0; w_strb <= 0;
      s_axil_bvalid <= 1'b0; s_axil_bresp <= OKAY;
      for (i = 0; i < N_RW; i = i + 1) regs[i] <= {DATA_W{1'b0}};
    end else begin
      if (s_axil_awvalid && s_axil_awready) begin aw_have <= 1'b1; aw_idx <= s_axil_awaddr[ADDR_W-1:SB]; end
      if (s_axil_wvalid && s_axil_wready) begin w_have <= 1'b1; w_data <= s_axil_wdata; w_strb <= s_axil_wstrb; end
      if (aw_have && w_have && !s_axil_bvalid) begin
        aw_have <= 1'b0; w_have <= 1'b0; s_axil_bvalid <= 1'b1;
        if (aw_idx < N_RW) begin
          s_axil_bresp <= OKAY; reg_wr[aw_idx] <= 1'b1;
          for (b = 0; b < DATA_W / 8; b = b + 1)
            if (w_strb[b]) regs[aw_idx][b*8 +: 8] <= w_data[b*8 +: 8];
        end else s_axil_bresp <= SLVERR;
      end
      if (s_axil_bvalid && s_axil_bready) s_axil_bvalid <= 1'b0;
    end
  end

  // ---- read ----
  wire [IW-1:0] ar_idx = s_axil_araddr[ADDR_W-1:SB];
  assign s_axil_arready = !s_axil_rvalid;
  always @(posedge clk) begin
    if (rst) begin
      s_axil_rvalid <= 1'b0; s_axil_rdata <= 0; s_axil_rresp <= OKAY;
    end else begin
      if (s_axil_arvalid && s_axil_arready) begin
        s_axil_rvalid <= 1'b1;
        if (ar_idx < N_RW) begin s_axil_rdata <= regs[ar_idx]; s_axil_rresp <= OKAY; end
        else if (ar_idx < N_RW + N_RO) begin s_axil_rdata <= reg_in[(ar_idx - N_RW) * DATA_W +: DATA_W]; s_axil_rresp <= OKAY; end
        else begin s_axil_rdata <= {DATA_W{1'b0}}; s_axil_rresp <= SLVERR; end
      end else if (s_axil_rvalid && s_axil_rready) s_axil_rvalid <= 1'b0;
    end
  end
`ifdef FORMAL
  // ---------------- formal properties (SymbiYosys: formal/axil_regs.sby) ----------------
  // The environment is any AXI4-Lite master that keeps a valid and its payload steady until ready. The bank must
  // then (1) hold bvalid/rvalid and their payloads until ready, (2) never have more than one write or one read
  // outstanding, (3) answer only requests it has received in full, with the right response code, and (4) keep, for
  // a register the solver picks, the value its writes gave it, and return that value when it is read.
  reg f_past = 1'b0;
  always @(posedge clk) f_past <= 1'b1;
  initial assume (rst);
  always @(posedge clk) if (f_past && !$past(rst)) begin
    if ($past(s_axil_awvalid && !s_axil_awready)) assume (s_axil_awvalid && $stable(s_axil_awaddr));
    if ($past(s_axil_wvalid && !s_axil_wready)) assume (s_axil_wvalid && $stable(s_axil_wdata) && $stable(s_axil_wstrb));
    if ($past(s_axil_arvalid && !s_axil_arready)) assume (s_axil_arvalid && $stable(s_axil_araddr));
  end
  reg [1:0] f_aw, f_w, f_ar;                                  // received and not yet answered
  always @(posedge clk)
    if (rst) begin f_aw <= 0; f_w <= 0; f_ar <= 0; end
    else begin
      f_aw <= f_aw + (s_axil_awvalid && s_axil_awready) - (s_axil_bvalid && s_axil_bready);
      f_w  <= f_w  + (s_axil_wvalid && s_axil_wready)   - (s_axil_bvalid && s_axil_bready);
      f_ar <= f_ar + (s_axil_arvalid && s_axil_arready) - (s_axil_rvalid && s_axil_rready);
    end
  (* anyconst *) reg [IW-1:0] f_watch;
  reg [DATA_W-1:0] f_shadow, f_expect; reg [IW-1:0] f_awi, f_ari; reg [DATA_W-1:0] f_wd; reg [DATA_W/8-1:0] f_ws;
  integer fb;
  always @(posedge clk) begin
    if (rst) f_shadow <= 0;
    else if (f_aw == 1 && f_w == 1 && !s_axil_bvalid && f_awi == f_watch && f_watch < N_RW)
      for (fb = 0; fb < DATA_W / 8; fb = fb + 1) if (f_ws[fb]) f_shadow[fb*8 +: 8] <= f_wd[fb*8 +: 8];
    if (s_axil_awvalid && s_axil_awready) f_awi <= s_axil_awaddr[ADDR_W-1:SB];
    if (s_axil_wvalid && s_axil_wready) begin f_wd <= s_axil_wdata; f_ws <= s_axil_wstrb; end
    if (s_axil_arvalid && s_axil_arready) begin
      f_ari <= ar_idx;
      f_expect <= (f_watch < N_RW) ? regs[f_watch] : (f_watch < N_RW + N_RO) ? reg_in[(f_watch - N_RW) * DATA_W +: DATA_W] : 0;
    end
  end
  always @(posedge clk) if (f_past && !$past(rst) && !rst) begin
    if ($past(s_axil_bvalid && !s_axil_bready)) assert (s_axil_bvalid && $stable(s_axil_bresp));
    if ($past(s_axil_rvalid && !s_axil_rready)) assert (s_axil_rvalid && $stable(s_axil_rdata) && $stable(s_axil_rresp));
    assert (f_aw <= 1 && f_w <= 1 && f_ar <= 1);
    if (s_axil_bvalid) assert (f_aw == 1 && f_w == 1);
    assert (s_axil_rvalid == (f_ar == 1));
    if (f_watch < N_RW) assert (regs[f_watch] == f_shadow);
    if (s_axil_bvalid) assert (s_axil_bresp == ((f_awi < N_RW) ? OKAY : SLVERR));
    if (s_axil_rvalid && f_ari == f_watch) begin
      assert (s_axil_rresp == ((f_watch < N_RW + N_RO) ? OKAY : SLVERR));
      assert (s_axil_rdata == f_expect);
    end
    // invariants that make the proof inductive
    assert (aw_have == (f_aw == 1 && !s_axil_bvalid));
    assert (w_have == (f_w == 1 && !s_axil_bvalid));
    if (f_aw == 1) assert (aw_idx == f_awi);
    if (w_have) assert (w_data == f_wd && w_strb == f_ws);
  end
  always @(posedge clk) if (f_past && $past(rst)) assert (!s_axil_bvalid && !s_axil_rvalid);
`endif
endmodule
