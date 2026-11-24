// UART transmitter and receiver with a FIFO on each side. Hand-written curated IP; no part is generated.
//
// Frame: one start bit (0), DATA_BITS data bits LSB first, an optional parity bit, STOP_BITS stop bits (1).
// Every bit lasts CLK_DIV clock cycles (CLK_DIV = clock frequency / baud rate, rounded).
//
// Parameters
//   CLK_DIV    8..65535   clock cycles per bit
//   DATA_BITS  5..9       data bits per frame
//   PARITY     0, 1, 2    none, odd, even
//   STOP_BITS  1, 2       stop bits (the receiver checks every one of them)
//   FIFO_AW    1..8       each FIFO holds 2**FIFO_AW frames
//
// Transmit: write tx_data with tx_valid/tx_ready. Receive: read rx_data with rx_valid/rx_ready;
// rx_parity_err and rx_frame_err belong to the frame on rx_data. When the receive FIFO is full a new
// frame is dropped and rx_overrun pulses for one cycle. Reset is synchronous and active high.
module barg_uart #(
  parameter integer CLK_DIV   = 868,
  parameter integer DATA_BITS = 8,
  parameter integer PARITY    = 0,
  parameter integer STOP_BITS = 1,
  parameter integer FIFO_AW   = 4
) (
  input  wire                 clk,
  input  wire                 rst,
  input  wire [DATA_BITS-1:0] tx_data,
  input  wire                 tx_valid,
  output wire                 tx_ready,
  output wire [DATA_BITS-1:0] rx_data,
  output wire                 rx_valid,
  input  wire                 rx_ready,
  output wire                 rx_parity_err,
  output wire                 rx_frame_err,
  output reg                  rx_overrun,
  output wire                 txd,
  input  wire                 rxd
);
  localparam integer PB = (PARITY != 0) ? 1 : 0;
  localparam integer NB = 1 + DATA_BITS + PB + STOP_BITS;   // bits in a frame, start bit included
  localparam integer NS = DATA_BITS + PB + STOP_BITS;       // bits the receiver samples after the start bit
  localparam integer CW = $clog2(CLK_DIV + 1);
  localparam integer BW = $clog2(NB + 1);
  // The receive logic sees the line two cycles late (synchroniser) and enters R_START one cycle after that,
  // so waiting HALF more cycles there samples the start bit at CLK_DIV/2 after its falling edge.
  // A start bit is a falling edge, so after a frame error (break) the receiver waits for the line to rise.
  localparam integer HALF = CLK_DIV / 2 - 1;

  // ---------------- transmit ----------------
  wire [DATA_BITS-1:0] tq;
  wire                 tq_valid;
  reg                  t_busy;
  barg_fifo #(.W(DATA_BITS), .AW(FIFO_AW)) u_txq (
    .clk(clk), .rst(rst), .in_data(tx_data), .in_valid(tx_valid), .in_ready(tx_ready),
    .out_data(tq), .out_valid(tq_valid), .out_ready(!t_busy)
  );
  wire t_par = (PARITY == 1) ? ~^tq : ^tq;
  wire [NB-1:0] t_frame;
  generate
    if (PB) begin : g_tpar
      assign t_frame = {{STOP_BITS{1'b1}}, t_par, tq, 1'b0};
    end else begin : g_tnopar
      assign t_frame = {{STOP_BITS{1'b1}}, tq, 1'b0};
    end
  endgenerate
  reg [NB-1:0] t_sh;
  reg [CW-1:0] t_cnt;
  reg [BW-1:0] t_left;
  reg          t_out;
  assign txd = t_out;
  always @(posedge clk) begin
    if (rst) begin
      t_busy <= 1'b0; t_out <= 1'b1; t_sh <= {NB{1'b1}}; t_cnt <= 0; t_left <= 0;
    end else if (!t_busy) begin
      t_out <= 1'b1;
      if (tq_valid) begin
        t_busy <= 1'b1; t_sh <= t_frame; t_out <= t_frame[0];
        t_left <= NB[BW-1:0]; t_cnt <= CLK_DIV[CW-1:0] - 1'b1;
      end
    end else if (t_cnt != 0) begin
      t_cnt <= t_cnt - 1'b1;
    end else if (t_left == 1) begin
      t_busy <= 1'b0; t_out <= 1'b1;
    end else begin
      t_sh <= t_sh >> 1; t_out <= t_sh[1];
      t_left <= t_left - 1'b1; t_cnt <= CLK_DIV[CW-1:0] - 1'b1;
    end
  end

  // ---------------- receive ----------------
  reg r_s1, r_s, r_prev;                // two-flop synchroniser, and the line one cycle before
  always @(posedge clk) begin
    if (rst) begin r_s1 <= 1'b1; r_s <= 1'b1; r_prev <= 1'b1; end
    else begin r_s1 <= rxd; r_s <= r_s1; r_prev <= r_s; end
  end
  localparam [1:0] R_IDLE = 2'd0, R_START = 2'd1, R_BITS = 2'd2;
  reg [1:0]    r_st;
  reg [CW-1:0] r_cnt;
  reg [BW-1:0] r_n;
  reg [NS-1:0] r_sh;
  reg          r_push;
  wire [NS-1:0] r_got = {r_s, r_sh[NS-1:1]};
  wire [DATA_BITS-1:0] r_data = r_got[DATA_BITS-1:0];
  wire          r_perr = (PB == 0) ? 1'b0 : ((^r_got[DATA_BITS:0]) != (PARITY == 1));
  wire          r_ferr = ~&r_got[NS-1:NS-STOP_BITS];
  reg [DATA_BITS+1:0] r_word;
  always @(posedge clk) begin
    r_push <= 1'b0;
    if (rst) begin
      r_st <= R_IDLE; r_cnt <= 0; r_n <= 0; r_sh <= 0; r_word <= 0;
    end else case (r_st)
      R_IDLE: if (r_prev && !r_s) begin   // a falling edge: after a break the line must rise first
                r_st <= R_START; r_cnt <= HALF[CW-1:0] - 1'b1; end
      R_START: if (r_cnt != 0) r_cnt <= r_cnt - 1'b1;
               else if (r_s) r_st <= R_IDLE;                    // a glitch, not a start bit
               else begin r_st <= R_BITS; r_cnt <= CLK_DIV[CW-1:0] - 1'b1; r_n <= 0; end
      default: if (r_cnt != 0) r_cnt <= r_cnt - 1'b1;
               else begin
                 r_sh <= r_got;
                 if (r_n == NS - 1) begin
                   r_st <= R_IDLE; r_push <= 1'b1; r_word <= {r_ferr, r_perr, r_data};
                 end else begin
                   r_n <= r_n + 1'b1; r_cnt <= CLK_DIV[CW-1:0] - 1'b1;
                 end
               end
    endcase
  end
  wire                 rq_in_ready;
  wire [DATA_BITS+1:0] rq;
  always @(posedge clk) rx_overrun <= !rst && r_push && !rq_in_ready;
  barg_fifo #(.W(DATA_BITS + 2), .AW(FIFO_AW)) u_rxq (
    .clk(clk), .rst(rst), .in_data(r_word), .in_valid(r_push), .in_ready(rq_in_ready),
    .out_data(rq), .out_valid(rx_valid), .out_ready(rx_ready)
  );
  assign rx_data       = rq[DATA_BITS-1:0];
  assign rx_parity_err = rq[DATA_BITS];
  assign rx_frame_err  = rq[DATA_BITS+1];
endmodule
