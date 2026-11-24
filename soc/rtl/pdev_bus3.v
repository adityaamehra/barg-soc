module pdev_bus3(
    input  [31:0] pa,
    input         pw,
    input         pr,
    input  [31:0] gpio_rdata,
    input  [31:0] spi_rdata,
    input  [31:0] i2c_rdata,
    input  [31:0] kbd_rdata,
    input  [31:0] mouse_rdata,
    output        gpio_we,
    output        spi_we,
    output        i2c_we,
    output        kbd_we,
    output        mouse_we,
    output        kbd_re,
    output        mouse_re,
    output [31:0] prdata
);

    wire [3:0] dev = pa[11:8];

    // Write enable signals
    assign gpio_we = pw & (dev == 4'b0000);
    assign spi_we  = pw & (dev == 4'b0001);
    assign i2c_we  = pw & (dev == 4'b0010);
    assign kbd_we  = pw & (dev == 4'b0011);
    assign mouse_we = pw & (dev == 4'b0100);

    // Read enable signals
    assign kbd_re  = pr & (dev == 4'b0011);
    assign mouse_re = pr & (dev == 4'b0100);

    // Read data multiplexer
    assign prdata = (dev == 4'b0000) ? gpio_rdata :
                    (dev == 4'b0001) ? spi_rdata  :
                    (dev == 4'b0010) ? i2c_rdata  :
                    (dev == 4'b0011) ? kbd_rdata  :
                    (dev == 4'b0100) ? mouse_rdata :
                    32'b0;

endmodule
