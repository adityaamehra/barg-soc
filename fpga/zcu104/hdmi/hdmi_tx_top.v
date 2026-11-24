// Stage 1 of the HDMI output on the ZCU104 (xczu7ev): a colour-bar test picture, 1280x720 at about 60 Hz, over the board's HDMI TX connector (P7, top port).
//   * data: GTH channels X0Y16..18 (quad 227) at 781.25 Mb/s per lane, 20-bit words, TMDS encoded in tmds_enc2 (blue lane 0, green lane 1, red lane 2)
//   * TMDS clock: a 78.125 MHz LVDS clock from the fabric (pins H9/G9) into the SN65DP159 retimer's IN_CLK
//   * transceiver reference clock: HDMI_DRU_CLOCK (156.25 MHz from the board's clock generator, quad 226 MGTREFCLK1), used by quad 227 as its south reference clock
//   * HDMI_TX_EN (A2) high enables the retimer's outputs; the retimer runs on its defaults (no I2C)
module hdmi_tx_top (
  input  wire        clk125_p, clk125_n,          // CLK_125 (LVDS)
  input  wire        gt_refclk_p, gt_refclk_n,    // HDMI_DRU_CLOCK, 156.25 MHz
  output wire [2:0]  hdmi_tx_p, hdmi_tx_n,        // HDMI_TX0..2
  output wire        hdmi_clk_p, hdmi_clk_n,      // HDMI_TX_LVDS_OUT
  output wire        hdmi_tx_en,
  input  wire        hdmi_hpd,
  output wire [1:0]  led                          // led[0]: transmitters ready, led[1]: pixel clock PLL locked
);
  // free-running clock for the transceiver reset logic and DRP: 125 MHz / 5 = 25 MHz (the wizard allows 6.25 to 39 MHz at this line rate)
  wire clk125_ib, clk25;
  IBUFDS u_ib125 (.I(clk125_p), .IB(clk125_n), .O(clk125_ib));
  BUFGCE_DIV #(.BUFGCE_DIVIDE(5)) u_div (.I(clk125_ib), .CE(1'b1), .CLR(1'b0), .O(clk25));
  reg [7:0] por = 0;
  always @(posedge clk25) if (por != 8'hFF) por <= por + 1'b1;
  wire reset_all_por = (por != 8'hFF);
  wire reset_all = reset_all_por | vio_reset;

  // reference clock from quad 226
  wire refclk;
  IBUFDS_GTE4 #(.REFCLK_EN_TX_PATH(1'b0), .REFCLK_HROW_CK_SEL(2'b00), .REFCLK_ICNTL_RX(2'b00)) u_refclk (.I(gt_refclk_p), .IB(gt_refclk_n), .CEB(1'b0), .O(refclk), .ODIV2());

  wire usrclk2, tx_active, tx_done;
  wire [2:0] pgood, pmadone, cpll_lock;
  wire [2:0] vio_pol; wire vio_en, vio_reset; wire [3:0] vio_swing;
  wire [59:0] txdata;
  wire [19:0] w_b, w_g, w_r;
  assign txdata = {w_r, w_g, w_b};      // channel 0 = bits [19:0] = blue
  wire [2:0] txp, txn;
  hdmi_gt u_gt (
    .gtwiz_userclk_tx_reset_in(1'b0),
    .gtwiz_userclk_tx_srcclk_out(), .gtwiz_userclk_tx_usrclk_out(), .gtwiz_userclk_tx_usrclk2_out(usrclk2), .gtwiz_userclk_tx_active_out(tx_active),
    .gtwiz_userclk_rx_active_in(1'b1),
    .gtwiz_reset_clk_freerun_in(clk25), .gtwiz_reset_all_in(reset_all),
    .gtwiz_reset_tx_pll_and_datapath_in(1'b0), .gtwiz_reset_tx_datapath_in(1'b0),
    .gtwiz_reset_rx_pll_and_datapath_in(1'b0), .gtwiz_reset_rx_datapath_in(1'b0),
    .gtwiz_reset_rx_cdr_stable_out(), .gtwiz_reset_tx_done_out(tx_done), .gtwiz_reset_rx_done_out(),
    .gtwiz_userdata_tx_in(txdata), .gtwiz_userdata_rx_out(),
    .drpclk_in({3{clk25}}),
    .gthrxn_in(3'b000), .gthrxp_in(3'b000),
    .gtrefclk0_in(3'b000),
    .rxusrclk_in({3{usrclk2}}), .rxusrclk2_in({3{usrclk2}}),
    .cpllrefclksel_in({3{3'b110}}),          // CPLL reference: GTSOUTHREFCLK1
    .gtsouthrefclk1_in({3{refclk}}),
    .gthtxn_out(txn), .gthtxp_out(txp), .gtpowergood_out(pgood), .rxoutclk_out(), .rxpmaresetdone_out(), .txpmaresetdone_out(pmadone),
    .txoutclk_out(), .cplllock_out(cpll_lock),
    .txpolarity_in(vio_pol), .txdiffctrl_in({3{vio_swing}})
  );
  assign hdmi_tx_p = txp; assign hdmi_tx_n = txn;

  // video stream in the transmitter's user clock domain (39.0625 MHz, two pixels per clock)
  hdmi_stream u_vid (.clk(usrclk2), .rst(!tx_done), .w_blue(w_b), .w_green(w_g), .w_red(w_r), .vsync_o());

  // TMDS clock: 78.125 MHz = 2 x usrclk2 from an MMCM, output through an ODDR as a clean 50% clock
  wire mmcm_fb, mmcm_clk78, mmcm_locked, clk78;
  MMCME4_BASE #(.CLKIN1_PERIOD(25.6), .CLKFBOUT_MULT_F(24.0), .DIVCLK_DIVIDE(1), .CLKOUT0_DIVIDE_F(12.0)) u_mmcm (
    .CLKIN1(usrclk2), .CLKFBIN(mmcm_fb), .CLKFBOUT(mmcm_fb), .CLKOUT0(mmcm_clk78), .LOCKED(mmcm_locked), .PWRDWN(1'b0), .RST(!tx_active),
    .CLKOUT0B(), .CLKOUT1(), .CLKOUT1B(), .CLKOUT2(), .CLKOUT2B(), .CLKOUT3(), .CLKOUT3B(), .CLKOUT4(), .CLKOUT5(), .CLKOUT6(), .CLKFBOUTB());
  BUFG u_bufg78 (.I(mmcm_clk78), .O(clk78));
  wire tmds_clk;
  ODDRE1 #(.SRVAL(1'b0)) u_oddr (.C(clk78), .D1(1'b1), .D2(1'b0), .SR(1'b0), .Q(tmds_clk));
  OBUFDS u_obclk (.I(tmds_clk), .O(hdmi_clk_p), .OB(hdmi_clk_n));

  assign hdmi_tx_en = vio_en;
  assign led = {mmcm_locked, tx_done};
  // debug window over JTAG (Vivado hardware manager): status in, lane polarity / swing / retimer enable / transceiver reset out
  vio_hdmi u_vio (.clk(clk25),
    .probe_in0(tx_done), .probe_in1(tx_active), .probe_in2(mmcm_locked), .probe_in3(pgood), .probe_in4(pmadone), .probe_in5(cpll_lock), .probe_in6(hdmi_hpd),
    .probe_out0(vio_pol), .probe_out1(vio_en), .probe_out2(vio_reset), .probe_out3(vio_swing));
endmodule
