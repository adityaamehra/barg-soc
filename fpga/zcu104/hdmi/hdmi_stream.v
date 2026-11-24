// 1280x720 video stream, two pixels per clock (clk = pixel clock / 2 = 39.0625 MHz for a 78.125 MHz pixel clock): timing generator, colour-bar test pattern
// (or the SoC's frame, see FRAME_SRC later) and the three TMDS channels. Output: the three 20-bit words for the transceivers (blue, green, red).
// Timing (pixels): H 1280 + 110 + 40 + 220 = 1650, V 720 + 5 + 5 + 59 = 789; at 78.125 MHz that is 60.01 Hz. Sync polarity positive, like 720p60.
module hdmi_stream (
  input  wire        clk,
  input  wire        rst,
  output wire [19:0] w_blue, w_green, w_red,
  output reg         vsync_o
);
  localparam HA = 640, HFP = 55, HS = 20, HBP = 110, HT = HA + HFP + HS + HBP;   // in clocks (2 pixels each): 825
  localparam VA = 720, VFP = 5, VS = 5, VBP = 59, VT = VA + VFP + VS + VBP;      // 789 lines
  reg [11:0] hc = 0; reg [11:0] vc = 0;
  always @(posedge clk) begin
    if (rst) begin hc <= 0; vc <= 0; end
    else if (hc == HT - 1) begin hc <= 0; vc <= (vc == VT - 1) ? 0 : vc + 1; end
    else hc <= hc + 1;
  end
  wire de    = (hc < HA) && (vc < VA);
  wire hsync = (hc >= HA + HFP) && (hc < HA + HFP + HS);
  wire vsync = (vc >= VA + VFP) && (vc < VA + VFP + VS);
  always @(posedge clk) vsync_o <= vsync;
  // colour bars: eight bars of 80 clocks (160 pixels); a white frame line at the picture's edge so that cropping is visible
  wire [2:0] bar = hc < 80 ? 3'd0 : hc < 160 ? 3'd1 : hc < 240 ? 3'd2 : hc < 320 ? 3'd3 : hc < 400 ? 3'd4 : hc < 480 ? 3'd5 : hc < 560 ? 3'd6 : 3'd7;
  reg [23:0] rgb;
  always @* begin
    case (bar)
      3'd0: rgb = 24'hFFFFFF; 3'd1: rgb = 24'hFFFF00; 3'd2: rgb = 24'h00FFFF; 3'd3: rgb = 24'h00FF00;
      3'd4: rgb = 24'hFF00FF; 3'd5: rgb = 24'hFF0000; 3'd6: rgb = 24'h0000FF; default: rgb = 24'h000000;
    endcase
    if (hc == 0 || hc == HA - 1 || vc == 0 || vc == VA - 1) rgb = 24'hFFFFFF;
  end
  reg de_q, hs_q, vs_q; reg [23:0] rgb_q;
  always @(posedge clk) begin de_q <= de; hs_q <= hsync; vs_q <= vsync; rgb_q <= rgb; end    // the same colour for both pixels of a clock in the test pattern
  tmds_enc2 u_b (.clk(clk), .de(de_q), .c({vs_q, hs_q}), .d0(rgb_q[7:0]),   .d1(rgb_q[7:0]),   .q(w_blue));
  tmds_enc2 u_g (.clk(clk), .de(de_q), .c(2'b00),        .d0(rgb_q[15:8]),  .d1(rgb_q[15:8]),  .q(w_green));
  tmds_enc2 u_r (.clk(clk), .de(de_q), .c(2'b00),        .d0(rgb_q[23:16]), .d1(rgb_q[23:16]), .q(w_red));
endmodule
