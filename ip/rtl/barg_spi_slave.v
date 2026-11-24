// SPI slave, one word per chip-select frame. Hand-written curated IP; no part is generated.
//
// Parameters
//   DATA_W     1..64   bits per frame
//   CPOL, CPHA 0, 1    the SPI mode, as seen from the master
//   LSB_FIRST  0, 1    bit order on the wire
//
// sclk, cs_n (active low) and mosi come from the master and are passed through two synchroniser flip-flops (a third gives the edge
// detector its previous value), so the slave needs each half SCLK period to last at least 4 clk cycles (SCLK <= clk / 8). tx_data is read on the clk
// cycle that sees cs_n fall (tx_load pulses then), so hold it from before cs_n falls until tx_load. The word is
// shifted out on miso; rx_data holds the word read from mosi for one cycle of rx_valid, on the last sampling edge.
// A frame that ends before DATA_W bits pulses rx_short instead; clocks past DATA_W bits are ignored.
// miso is driven always (0 outside a frame); a shared bus must gate it with cs_n outside. Reset is synchronous, active high.
module barg_spi_slave #(
  parameter integer DATA_W    = 8,
  parameter integer CPOL      = 0,
  parameter integer CPHA      = 0,
  parameter integer LSB_FIRST = 0
) (
  input  wire              clk,
  input  wire              rst,
  input  wire              sclk,
  input  wire              cs_n,
  input  wire              mosi,
  output reg               miso,
  input  wire [DATA_W-1:0] tx_data,
  output reg               tx_load,
  output reg  [DATA_W-1:0] rx_data,
  output reg               rx_valid,
  output reg               rx_short
);
  localparam integer CW = $clog2(DATA_W + 1);
  reg m_sclk, s_sclk, p_sclk, m_cs, s_cs, p_cs, m_mosi, s_mosi;   // first flop of each chain only absorbs metastability
  reg [CW-1:0]     cnt;            // sampling edges seen in this frame
  reg [DATA_W-1:0] tx_sh, rx_sh;
  wire sclk_edge = s_sclk != p_sclk;
  wire lead      = sclk_edge && (s_sclk != CPOL[0]);
  wire trail     = sclk_edge && (s_sclk == CPOL[0]);
  wire samp      = (CPHA == 0) ? lead : trail;
  wire shft      = (CPHA == 0) ? trail : lead;
  wire cs_fall   = p_cs && !s_cs;
  wire cs_rise   = !p_cs && s_cs;
  wire done      = (cnt == DATA_W);
  wire [DATA_W-1:0] rx_next = LSB_FIRST ? ({s_mosi, rx_sh} >> 1) : {rx_sh, s_mosi};
  wire out_bit   = LSB_FIRST ? tx_sh[0] : tx_sh[DATA_W-1];
  wire [DATA_W-1:0] tx_next = LSB_FIRST ? (tx_sh >> 1) : (tx_sh << 1);
  wire first_bit = LSB_FIRST ? tx_data[0] : tx_data[DATA_W-1];
  wire [DATA_W-1:0] tx_after_first = LSB_FIRST ? (tx_data >> 1) : (tx_data << 1);
  always @(posedge clk) begin
    tx_load <= 1'b0; rx_valid <= 1'b0; rx_short <= 1'b0;
    if (rst) begin
      m_sclk <= CPOL[0]; s_sclk <= CPOL[0]; p_sclk <= CPOL[0]; m_cs <= 1'b1; s_cs <= 1'b1; p_cs <= 1'b1; m_mosi <= 1'b0; s_mosi <= 1'b0;
      cnt <= 0; tx_sh <= 0; rx_sh <= 0; rx_data <= 0; miso <= 1'b0;
    end else begin
      m_sclk <= sclk; s_sclk <= m_sclk; p_sclk <= s_sclk; m_cs <= cs_n; s_cs <= m_cs; p_cs <= s_cs; m_mosi <= mosi; s_mosi <= m_mosi;
      if (cs_fall) begin
        cnt <= 0; rx_sh <= 0; tx_load <= 1'b1;
        if (CPHA == 0) begin miso <= first_bit; tx_sh <= tx_after_first; end
        else tx_sh <= tx_data;
      end else if (cs_rise) begin
        if (cnt != 0 && !done) rx_short <= 1'b1;
        miso <= 1'b0;
      end else if (!s_cs) begin
        if (samp && !done) begin
          rx_sh <= rx_next; cnt <= cnt + 1'b1;
          if (cnt == DATA_W - 1) begin rx_data <= rx_next; rx_valid <= 1'b1; end
        end
        if (shft && !done) begin miso <= out_bit; tx_sh <= tx_next; end
      end
    end
  end
endmodule
