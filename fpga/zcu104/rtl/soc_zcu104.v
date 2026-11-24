// Board wrapper of the quad-core Linux SoC (built with build_quad5.py --ext-mem; its top is renamed soc_core by export.py) for the ZCU104.
//   * clock/reset: aclk (PL clock 100 MHz from the PS), aresetn (processor system reset), run (PS GPIO: 0 holds the SoC in reset while the image is loaded)
//   * memory: the SoC's AXI4 master (32 bit, no ids) goes to the PS DDR through a HP port. The SoC's RAM is 64 MB at 0x8000_0000; the wrapper moves it to DDR address 0x4000_0000.
//   * console: the SoC's byte interface (rx_valid/uart_tx_valid) is serialised by the curated barg_uart (115200 8N1 at CLK_HZ)
//   * PS/2 keyboard and mouse: open-drain pins (a low request drives 0, otherwise the pin floats and the board's pull-up and the device decide); inputs pass two flip-flops
//   * video: the GPU's scan-out (hsync, vsync, rgb565 cut to rgb332) is brought out as vid_* ports
module soc_zcu104 #(parameter integer CLK_HZ = 20000000) (
  (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK" *)
  (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF m_axi, ASSOCIATED_RESET aresetn, FREQ_HZ 20000000" *)
  input  wire        aclk,
  (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST" *)
  (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
  input  wire        aresetn,
  input  wire        run,
  // console (PMOD)
  input  wire        uart_rxd,
  output wire        uart_txd,
  // PS/2 (PMOD, open drain)
  inout  wire        ps2k_clk, inout wire ps2k_dat,
  inout  wire        ps2m_clk, inout wire ps2m_dat,
  // video
  output wire        vid_hsync, output wire vid_vsync, output wire [7:0] vid_rgb332,   // red 3, green 3, blue 2 bits (the top bits of the GPU's rgb565), for a resistor-ladder VGA adapter on PMOD pins
  // status
  output wire [3:0]  status,
  // DDR (AXI4 master, 32 bit)
  output wire [5:0]  m_axi_awid,   output wire [31:0] m_axi_awaddr, output wire [7:0] m_axi_awlen, output wire [2:0] m_axi_awsize, output wire [1:0] m_axi_awburst,
  output wire [0:0]  m_axi_awlock, output wire [3:0]  m_axi_awcache, output wire [2:0] m_axi_awprot, output wire [3:0] m_axi_awqos, output wire m_axi_awvalid, input wire m_axi_awready,
  output wire [31:0] m_axi_wdata,  output wire [3:0]  m_axi_wstrb,   output wire       m_axi_wlast,   output wire m_axi_wvalid,  input wire m_axi_wready,
  input  wire [5:0]  m_axi_bid,    input  wire [1:0]  m_axi_bresp,   input  wire       m_axi_bvalid,  output wire m_axi_bready,
  output wire [5:0]  m_axi_arid,   output wire [31:0] m_axi_araddr,  output wire [7:0] m_axi_arlen,  output wire [2:0] m_axi_arsize, output wire [1:0] m_axi_arburst,
  output wire [0:0]  m_axi_arlock, output wire [3:0]  m_axi_arcache, output wire [2:0] m_axi_arprot, output wire [3:0] m_axi_arqos, output wire m_axi_arvalid, input wire m_axi_arready,
  input  wire [5:0]  m_axi_rid,    input  wire [31:0] m_axi_rdata,   input  wire [1:0] m_axi_rresp,  input  wire m_axi_rlast,    input wire m_axi_rvalid,  output wire m_axi_rready
);
  // The cores run on gated clocks (a latch and an AND per core, mapped to BUFGCE cells fed from the fabric); the rest of the SoC gets its clock through a BUFGCE too, so every
  // domain has a similar insertion delay (a direct BUFG next to gated BUFGCEs left 2 to 3 ns of skew and 0.3 ns of hold violation).
  wire clk_core;
`ifdef VERILATOR
  assign clk_core = aclk;
`else
  (* DONT_TOUCH = "true" *) BUFGCE u_core_clk (.I(aclk), .CE(1'b1), .O(clk_core));   // kept: opt_design would otherwise drop a BUFGCE with CE = 1 and leave this domain on the bare BUFG
`endif
  // reset: held while the PS has not released it (aresetn) or the image is still being loaded (run = 0); released synchronously
  reg [3:0] rs = 4'hF;
  always @(posedge clk_core) rs <= (!aresetn || !run) ? 4'hF : {rs[2:0], 1'b0};
  wire rst = rs[3];

  // console
  // The SoC hands over each transmitted byte as a one-cycle strobe and does not wait for the line, so the UART's transmit FIFO (256 frames) absorbs bursts at 115200 baud.
  wire [7:0] tx_data; wire tx_valid; wire [7:0] u_rx_data; wire u_rx_valid;
  barg_uart #(.CLK_DIV(CLK_HZ / 115200), .FIFO_AW(8)) u_uart (
    .clk(clk_core), .rst(rst), .tx_data(tx_data), .tx_valid(tx_valid), .tx_ready(),
    .rx_data(u_rx_data), .rx_valid(u_rx_valid), .rx_ready(1'b1),
    .rx_parity_err(), .rx_frame_err(), .rx_overrun(), .txd(uart_txd), .rxd(uart_rxd));

  // PS/2 pins
  wire kc_low, kd_low, mc_low, md_low;
  reg [1:0] kc_s, kd_s, mc_s, md_s;
  assign ps2k_clk = kc_low ? 1'b0 : 1'bz;  assign ps2k_dat = kd_low ? 1'b0 : 1'bz;
  assign ps2m_clk = mc_low ? 1'b0 : 1'bz;  assign ps2m_dat = md_low ? 1'b0 : 1'bz;
  always @(posedge clk_core) begin
    kc_s <= {kc_s[0], ps2k_clk}; kd_s <= {kd_s[0], ps2k_dat}; mc_s <= {mc_s[0], ps2m_clk}; md_s <= {md_s[0], ps2m_dat};
  end

  wire gpu_running, gpu_done, gpu_error, gpu_diverged; wire [15:0] gpu_rgb;
  assign vid_rgb332 = {gpu_rgb[15:13], gpu_rgb[10:8], gpu_rgb[4:3]};
  wire [31:0] araddr, awaddr; wire [31:0] bus_addr, bus_wdata; wire [15:0] gpio_out, gpio_oe; wire [3:0] spi_cs_n;
  wire uart_irq, spi_sclk, spi_mosi, i2c_scl_o, i2c_sda_o;
  soc_core u_soc (
    .clk(clk_core), .clk_pre(aclk), .rst(rst),
    .rx_valid(u_rx_valid), .rx_data(u_rx_data), .ext_s2(1'b0), .ext_s3(1'b0), .meip(1'b0),
    .uart_irq(uart_irq), .uart_tx_valid(tx_valid), .uart_tx_data(tx_data),
    .gpio_in(16'd0), .gpio_out(gpio_out), .gpio_oe(gpio_oe),
    .spi_miso(1'b0), .spi_sclk(spi_sclk), .spi_mosi(spi_mosi), .spi_cs_n(spi_cs_n),
    .i2c_scl_i(1'b1), .i2c_sda_i(1'b1), .i2c_scl_o(i2c_scl_o), .i2c_sda_o(i2c_sda_o),
    .ps2k_clk_i(kc_s[1]), .ps2k_dat_i(kd_s[1]), .ps2k_clk_low(kc_low), .ps2k_dat_low(kd_low),
    .ps2m_clk_i(mc_s[1]), .ps2m_dat_i(md_s[1]), .ps2m_clk_low(mc_low), .ps2m_dat_low(md_low),
    .bus_addr(bus_addr), .bus_wdata(bus_wdata),
    .gpu_running(gpu_running), .gpu_done(gpu_done), .gpu_error(gpu_error), .gpu_diverged(gpu_diverged),
    .gpu_hsync(vid_hsync), .gpu_vsync(vid_vsync), .gpu_de(), .gpu_rgb(gpu_rgb),
    .m_axi_arvalid(m_axi_arvalid), .m_axi_araddr(araddr), .m_axi_arlen(m_axi_arlen), .m_axi_arsize(m_axi_arsize), .m_axi_arburst(m_axi_arburst), .m_axi_arready(m_axi_arready),
    .m_axi_rready(m_axi_rready), .m_axi_rvalid(m_axi_rvalid), .m_axi_rdata(m_axi_rdata), .m_axi_rresp(m_axi_rresp), .m_axi_rlast(m_axi_rlast),
    .m_axi_awvalid(m_axi_awvalid), .m_axi_awaddr(awaddr), .m_axi_awlen(m_axi_awlen), .m_axi_awsize(m_axi_awsize), .m_axi_awburst(m_axi_awburst), .m_axi_awready(m_axi_awready),
    .m_axi_wvalid(m_axi_wvalid), .m_axi_wdata(m_axi_wdata), .m_axi_wstrb(m_axi_wstrb), .m_axi_wlast(m_axi_wlast), .m_axi_wready(m_axi_wready),
    .m_axi_bready(m_axi_bready), .m_axi_bvalid(m_axi_bvalid), .m_axi_bresp(m_axi_bresp));

  assign m_axi_araddr = 32'h4000_0000 | {6'd0, araddr[25:0]};
  assign m_axi_awaddr = 32'h4000_0000 | {6'd0, awaddr[25:0]};
  assign m_axi_awid = 6'd0; assign m_axi_arid = 6'd0;
  assign m_axi_awlock = 1'b0; assign m_axi_arlock = 1'b0; assign m_axi_awcache = 4'b0011; assign m_axi_arcache = 4'b0011;
  assign m_axi_awprot = 3'b000; assign m_axi_arprot = 3'b000; assign m_axi_awqos = 4'd0; assign m_axi_arqos = 4'd0;
  assign status = {gpu_diverged, gpu_error, gpu_running | gpu_done, uart_irq};
endmodule
