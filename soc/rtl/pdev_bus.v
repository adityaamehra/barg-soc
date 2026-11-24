module pdev_bus(
    input  [31:0] pa,
    input         pw,
    input  [31:0] gpio_rdata,
    input  [31:0] spi_rdata,
    input  [31:0] i2c_rdata,
    output        gpio_we,
    output        spi_we,
    output        i2c_we,
    output [31:0] prdata
);

// Device selection based on bits [11:8] of the address
wire [3:0] dev = pa[11:8];

// Write enable signals
assign gpio_we = pw & (dev == 4'b0000);
assign spi_we  = pw & (dev == 4'b0001);
assign i2c_we  = pw & (dev == 4'b0010);

// Read data multiplexer
assign prdata = (dev == 4'b0000) ? gpio_rdata :
                (dev == 4'b0001) ? spi_rdata  :
                (dev == 4'b0010) ? i2c_rdata  :
                32'b0;

endmodule
