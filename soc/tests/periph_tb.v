// The quad SoC with the peripheral window (--periph): the pins of the GPIO, the SPI master and the I2C master are wired to models. Like isa_quad_tb: all
// harts start at 0x8000_0000, the program ends by writing 0x80FFF000 (1 is a pass). GPIO: output pins read back through the input pins (pins 15:12 are held
// high from outside); SPI: MISO is wired to MOSI (loopback) and a monitor records the chip-select lines used; I2C: an open-drain bus with a slave at address
// 0x50 that acknowledges every byte of a write and answers a read with the bytes 3C, 3D, ... Prints PASS or FAIL like isa_quad_tb, then the monitor counts.
`ifdef PS2
`define PS2TIE , .ps2k_clk_i(1'b1), .ps2k_dat_i(1'b1), .ps2m_clk_i(1'b1), .ps2m_dat_i(1'b1)
`else
`define PS2TIE
`endif
module periph_tb;
`include "memview.vh"
  reg clk = 0, rst = 1;
  reg meip = 0, rx_valid = 0, s2 = 0, s3 = 0;
  reg [7:0] rx_data = 0;
  wire uart_irq, uart_tx_valid;
  wire [7:0] uart_tx_data;
  wire [15:0] gpio_out, gpio_oe;
  wire spi_sclk, spi_mosi, i2c_scl_o, i2c_sda_o;
  wire [3:0] spi_cs_n;
  wire [31:0] bus_addr, bus_wdata;
  reg [15:0] ext_in = 16'hF000;
  wire [15:0] gpio_in = (gpio_out & gpio_oe) | (ext_in & ~gpio_oe);
  // I2C bus: open drain with pull-ups; the slave drives SDA low through slv_sda = 0
  reg slv_sda = 1;
  wire scl = i2c_scl_o ? 1'b1 : 1'b0;
  wire sda = (i2c_sda_o ? 1'b1 : 1'b0) & slv_sda;
  reg [1023:0] hexfile;
  reg [31:0] tohost_addr;
  integer limit, cyc, done;
  reg [31:0] v;
  top dut (.clk(clk), .rst(rst), .rx_valid(rx_valid), .rx_data(rx_data), .ext_s2(s2), .ext_s3(s3), .meip(meip),
           .uart_irq(uart_irq), .uart_tx_valid(uart_tx_valid), .uart_tx_data(uart_tx_data), .bus_addr(bus_addr), .bus_wdata(bus_wdata),
           .gpio_in(gpio_in), .gpio_out(gpio_out), .gpio_oe(gpio_oe),
           .spi_miso(spi_mosi), .spi_sclk(spi_sclk), .spi_mosi(spi_mosi), .spi_cs_n(spi_cs_n),
           .i2c_scl_i(scl), .i2c_sda_i(sda), .i2c_scl_o(i2c_scl_o), .i2c_sda_o(i2c_sda_o) `PS2TIE);
  always #5 clk = ~clk;

  // SPI monitor: which chip selects were low during SCLK edges, and the number of SCLK rising edges
  integer sclk_edges = 0;
  reg [3:0] cs_seen = 0;
  always @(posedge spi_sclk) begin sclk_edges = sclk_edges + 1; cs_seen = cs_seen | ~spi_cs_n; end

  // I2C slave (address 0x50): counts START, STOP, written bytes; answers reads with 3C, 3D, ...
  reg inframe = 0, mode = 0, first = 1, addr_ok = 0, ack_next = 0, mnack = 0;
  integer bitn = 0, n_start = 0, n_stop = 0, n_wr = 0, n_rd = 0;
  reg [7:0] sbyte = 0, txb = 0;
  always @(negedge sda) if (scl === 1'b1 && !rst) begin n_start = n_start + 1; inframe = 1; bitn = 0; mode = 0; first = 1; slv_sda = 1; end
  always @(posedge sda) if (scl === 1'b1 && !rst) begin n_stop = n_stop + 1; inframe = 0; mode = 0; slv_sda = 1; end
  always @(posedge scl) if (inframe) begin
    bitn = bitn + 1;
    if (!mode && bitn <= 8) sbyte = {sbyte[6:0], sda};
    if (!mode && bitn == 8) begin
      if (first) begin addr_ok = (sbyte[7:1] == 7'h50); ack_next = addr_ok; end
      else begin ack_next = addr_ok; if (ack_next) n_wr = n_wr + 1; end
    end
    if (mode && bitn == 9) begin mnack = sda; n_rd = n_rd + 1; end
  end
  always @(negedge scl) if (inframe) begin
    if (bitn == 8) slv_sda = mode ? 1'b1 : !ack_next;
    else if (bitn == 9) begin
      bitn = 0;
      if (!mode && first) begin
        first = 0;
        if (addr_ok && sbyte[0]) begin mode = 1; txb = 8'h3C + n_rd; slv_sda = txb[7]; end else slv_sda = 1;
      end else if (mode) begin
        if (mnack) begin mode = 0; slv_sda = 1; end
        else begin txb = 8'h3C + n_rd; slv_sda = txb[7]; end
      end else slv_sda = 1;
    end else if (mode && bitn >= 1 && bitn <= 7) slv_sda = txb[7 - bitn];
  end

  initial begin
    if (!$value$plusargs("HEX=%s", hexfile)) begin $display("FAIL no HEX"); $finish; end
    if (!$value$plusargs("TOHOST=%h", tohost_addr)) tohost_addr = 32'h80FFF000;
    if (!$value$plusargs("LIMIT=%d", limit)) limit = 400000;
    #1;
    $readmemh(hexfile, dut.u_ram_main.u_ip.mem);
    repeat (3) @(posedge clk);
    rst <= 0;
    done = 0;
    for (cyc = 0; cyc < limit && !done; cyc = cyc + 1) begin
      @(posedge clk);
      v = `RAMW((tohost_addr - 32'h80000000) >> 2);
      if (v != 0) done = 1;
    end
    if (!done) $display("FAIL timeout after %0d cycles, tohost still 0", cyc);
    else if (v == 32'd1) $display("PASS in %0d cycles", cyc);
    else $display("FAIL tohost=%0d (check %0d) after %0d cycles", v, v >> 1, cyc);
    $display("MON sclk_edges=%0d cs_seen=%b i2c start=%0d stop=%0d wr=%0d rd=%0d", sclk_edges, cs_seen, n_start, n_stop, n_wr, n_rd);
    $finish;
  end
endmodule
