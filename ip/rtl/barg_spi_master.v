// SPI master, one word per transfer. Hand-written curated IP; no part is generated.
//
// Parameters
//   DATA_W     1..64      bits per transfer
//   CLK_DIV    1..65535   clock cycles per half SCLK period (SCLK = clk / (2 * CLK_DIV))
//   CPOL       0, 1       SCLK level when idle
//   CPHA       0, 1       0: sample on the leading edge, shift on the trailing edge; 1: shift on leading, sample on trailing
//   LSB_FIRST  0, 1       bit order on the wire
//   CS_W       1..16      chip-select lines (active low); tx_cs picks one, a value >= CS_W selects none
//
// A transfer starts on tx_valid && tx_ready. Chip select falls, half an SCLK period passes before the first edge
// and after the last, then chip select rises and rx_data holds the word read from miso for one cycle of rx_valid.
// Chip select stays high for at least CLK_DIV cycles between transfers. Reset is synchronous and active high.
// miso is sampled without a synchroniser: the slave is clocked by this SCLK, so it has half a period to settle.
module barg_spi_master #(
  parameter integer DATA_W    = 8,
  parameter integer CLK_DIV   = 4,
  parameter integer CPOL      = 0,
  parameter integer CPHA      = 0,
  parameter integer LSB_FIRST = 0,
  parameter integer CS_W      = 1
) (
  input  wire                                   clk,
  input  wire                                   rst,
  input  wire [DATA_W-1:0]                      tx_data,
  input  wire [$clog2(CS_W > 1 ? CS_W : 2)-1:0] tx_cs,
  input  wire                                   tx_valid,
  output wire                                   tx_ready,
  output reg  [DATA_W-1:0]                      rx_data,
  output reg                                    rx_valid,
  output reg                                    sclk,
  output reg                                    mosi,
  input  wire                                   miso,
  output reg  [CS_W-1:0]                        cs_n
);
  localparam integer CW = $clog2(CLK_DIV + 1);
  localparam integer EW = $clog2(2 * DATA_W + 1);
  localparam [1:0] S_IDLE = 2'd0, S_RUN = 2'd1, S_END = 2'd2, S_GAP = 2'd3;
  reg [1:0]        st;
  reg [CW-1:0]     cnt;
  reg [EW-1:0]     edges;          // SCLK edges still to make; the leading edges are the ones made when this is even
  reg [DATA_W-1:0] tx_sh, rx_sh;
  assign tx_ready = (st == S_IDLE);
  wire          out_bit  = LSB_FIRST ? tx_sh[0] : tx_sh[DATA_W-1];
  wire [DATA_W-1:0] tx_next = LSB_FIRST ? (tx_sh >> 1) : (tx_sh << 1);
  wire          first_bit = LSB_FIRST ? tx_data[0] : tx_data[DATA_W-1];
  wire [DATA_W-1:0] tx_after_first = LSB_FIRST ? (tx_data >> 1) : (tx_data << 1);
  wire [DATA_W-1:0] rx_next = LSB_FIRST ? ({miso, rx_sh} >> 1) : {rx_sh, miso};
  wire          leading  = !edges[0];
  wire          sample   = (CPHA == 0) ? leading : !leading;
  always @(posedge clk) begin
    rx_valid <= 1'b0;
    if (rst) begin
      st <= S_IDLE; cnt <= 0; edges <= 0; tx_sh <= 0; rx_sh <= 0; rx_data <= 0;
      sclk <= CPOL[0]; mosi <= 1'b0; cs_n <= {CS_W{1'b1}};
    end else case (st)
      S_IDLE: if (tx_valid) begin
        st <= S_RUN; cnt <= CLK_DIV[CW-1:0] - 1'b1; edges <= 2 * DATA_W;
        cs_n <= ~({{CS_W{1'b0}}, 1'b1} << tx_cs);
        if (CPHA == 0) begin mosi <= first_bit; tx_sh <= tx_after_first; end
        else tx_sh <= tx_data;
      end
      S_RUN: if (cnt != 0) cnt <= cnt - 1'b1;
        else begin
          sclk <= ~sclk; edges <= edges - 1'b1; cnt <= CLK_DIV[CW-1:0] - 1'b1;
          if (sample) rx_sh <= rx_next;
          else if (CPHA == 1 || edges != 1) begin mosi <= out_bit; tx_sh <= tx_next; end
          if (edges == 1) st <= S_END;
        end
      S_END: if (cnt != 0) cnt <= cnt - 1'b1;
        else begin
          cs_n <= {CS_W{1'b1}}; rx_data <= rx_sh; rx_valid <= 1'b1;
          st <= S_GAP; cnt <= CLK_DIV[CW-1:0] - 1'b1;
        end
      default: if (cnt != 0) cnt <= cnt - 1'b1; else st <= S_IDLE;
    endcase
  end
endmodule
