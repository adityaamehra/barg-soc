// I2C master, one byte per command. Hand-written curated IP; no part is generated.
//
// Parameters
//   CLK_DIV   2..65535   clock cycles per quarter SCL period (SCL = clk / (4 * CLK_DIV))
//   STRETCH   0, 1       1: wait while a slave holds SCL low (clock stretching); 0: ignore scl_i
//
// The lines are open-drain: scl_o / sda_o = 0 drives the line low and 1 releases it. Connect each to a tri-state
// buffer (line = o ? 1'bz : 1'b0) and read the pad back on scl_i / sda_i.
//
// One command per cmd_valid && cmd_ready. cmd_op: 0 write cmd_data, 1 read a byte (cmd_nack = answer NACK
// instead of ACK, for the last byte), 2 or 3 STOP only. For a byte, cmd_start sends a START (a repeated START
// inside a transaction) before it and cmd_stop a STOP after it. A byte sent with no transaction open always starts
// one. STOP only with no transaction open does nothing. After a byte without cmd_stop, SCL stays low and the next
// command continues the transaction. cmd_ready returns once the bus is back in the state the command leaves it.
// Do not follow a byte the master ACKed (a read without cmd_nack) with a START: the slave may still hold SDA low
// for its next bit, and the master then reports rsp_arb_lost. NACK the last byte first.
// rsp_valid pulses once per command: rsp_data is the byte read (or echoed back on a write), rsp_nack is 1 when the
// slave did not acknowledge a written byte, rsp_arb_lost is 1 when the master released SDA for a 1 and saw it low:
// the master then releases both lines and the command ends with no STOP. Reset is synchronous, active high.
module barg_i2c_master #(
  parameter integer CLK_DIV = 4,
  parameter integer STRETCH = 0
) (
  input  wire       clk,
  input  wire       rst,
  input  wire       cmd_valid,
  output wire       cmd_ready,
  input  wire [1:0] cmd_op,
  input  wire       cmd_start,
  input  wire       cmd_stop,
  input  wire       cmd_nack,
  input  wire [7:0] cmd_data,
  output reg        rsp_valid,
  output reg  [7:0] rsp_data,
  output reg        rsp_nack,
  output reg        rsp_arb_lost,
  output reg        scl_o,
  input  wire       scl_i,
  output reg        sda_o,
  input  wire       sda_i
);
  localparam integer CW = $clog2(CLK_DIV + 1);
  localparam [2:0] S_IDLE = 3'd0, S_START = 3'd1, S_DATA = 3'd2, S_ACK = 3'd3, S_STOP = 3'd4;
  reg [2:0]    st;
  reg [1:0]    q;                  // quarter of the current symbol
  reg [2:0]    bc;                 // data bit
  reg [CW-1:0] cnt;
  reg [7:0]    sh;
  reg          l_read, l_start, l_stop, l_nack;
  reg          active;             // a transaction is open: START sent, no STOP yet
  reg          m_scl, s_scl, m_sda, s_sda;
  assign cmd_ready = (st == S_IDLE);
  wire hold = (STRETCH != 0) && (q == 2'd1) && !s_scl;
  wire [CW-1:0] reload = CLK_DIV[CW-1:0] - 1'b1;
  always @(posedge clk) begin
    rsp_valid <= 1'b0;
    if (rst) begin
      st <= S_IDLE; q <= 0; bc <= 0; cnt <= 0; sh <= 0; active <= 1'b0;
      l_read <= 0; l_start <= 0; l_stop <= 0; l_nack <= 0;
      m_scl <= 1'b1; s_scl <= 1'b1; m_sda <= 1'b1; s_sda <= 1'b1;
      scl_o <= 1'b1; sda_o <= 1'b1; rsp_data <= 0; rsp_nack <= 0; rsp_arb_lost <= 0;
    end else begin
      m_scl <= scl_i; s_scl <= m_scl; m_sda <= sda_i; s_sda <= m_sda;
      if (st == S_IDLE) begin
        if (cmd_valid) begin
          l_read <= cmd_op == 2'd1; l_start <= cmd_start || !active; l_stop <= cmd_stop; l_nack <= cmd_nack;
          sh <= cmd_data; rsp_nack <= 1'b0; rsp_arb_lost <= 1'b0; q <= 0; bc <= 0; cnt <= reload;
          if (cmd_op[1]) begin
            if (active) begin st <= S_STOP; sda_o <= 1'b0; end
            else begin rsp_valid <= 1'b1; rsp_data <= 0; end
          end else if (cmd_start || !active) begin st <= S_START; sda_o <= 1'b1; end
          else begin st <= S_DATA; sda_o <= (cmd_op == 2'd1) ? 1'b1 : cmd_data[7]; end
        end
      end else if (!hold) begin
        if (cnt != 0) cnt <= cnt - 1'b1;
        else begin
          cnt <= reload;
          case (q)
            2'd0: begin q <= 2'd1; scl_o <= 1'b1; end
            2'd1: begin
              q <= 2'd2;
              if (st == S_START) sda_o <= 1'b0;
              else if (st == S_STOP) sda_o <= 1'b1;
            end
            2'd2: begin
              q <= 2'd3;
              if (st != S_STOP) scl_o <= 1'b0;
              if (st == S_DATA) begin
                sh <= {sh[6:0], s_sda};
                if (!l_read && sda_o && !s_sda) begin           // lost arbitration: let go of both lines
                  scl_o <= 1'b1; sda_o <= 1'b1; st <= S_IDLE; active <= 1'b0;
                  rsp_valid <= 1'b1; rsp_arb_lost <= 1'b1; rsp_data <= {sh[6:0], s_sda}; rsp_nack <= 1'b0;
                end
              end
              if (st == S_ACK && !l_read) rsp_nack <= s_sda;
            end
            2'd3: begin
              q <= 2'd0;
              case (st)
                S_START: begin active <= 1'b1; st <= S_DATA; bc <= 0; sda_o <= l_read ? 1'b1 : sh[7]; end
                S_DATA: if (bc == 3'd7) begin st <= S_ACK; sda_o <= l_read ? l_nack : 1'b1; end
                        else begin bc <= bc + 1'b1; sda_o <= l_read ? 1'b1 : sh[7]; end
                S_ACK: if (l_stop) begin st <= S_STOP; sda_o <= 1'b0; end
                       else begin st <= S_IDLE; rsp_valid <= 1'b1; rsp_data <= sh; end
                default: begin st <= S_IDLE; active <= 1'b0; rsp_valid <= 1'b1; rsp_data <= sh; end   // S_STOP
              endcase
            end
          endcase
        end
      end
    end
  end
endmodule
