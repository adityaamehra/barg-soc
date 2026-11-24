// Pin models of the peripheral window (GPIO loopback, SPI loopback, I2C slave at 0x50 answering reads with 3C, 3D, ...) for the testbenches of the --periph SoC.
// Included inside a testbench module that has clk and rst; declares the wires the SoC's pins connect to.
  wire [15:0] gpio_out, gpio_oe;
  wire spi_sclk, spi_mosi, i2c_scl_o, i2c_sda_o;
  wire [3:0] spi_cs_n;
  reg [15:0] ext_in = 16'hF000;
  wire [15:0] gpio_in = (gpio_out & gpio_oe) | (ext_in & ~gpio_oe);
  // I2C bus: open drain with pull-ups; the slave drives SDA low through slv_sda = 0
  reg slv_sda = 1;
  wire scl = i2c_scl_o ? 1'b1 : 1'b0;
  wire sda = (i2c_sda_o ? 1'b1 : 1'b0) & slv_sda;
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

