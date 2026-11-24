module pdev_bus2(
    input  [31:0] pa,
    input         pw,
    input  [31:0] gpio_rdata,
    input  [31:0] spi_rdata,
    input  [31:0] i2c_rdata,
    input  [31:0] kbd_rdata,
    input  [31:0] mouse_rdata,
    input  [31:0] disp_rdata,
    input  [31:0] fb_rdata,
    output        gpio_we,
    output        spi_we,
    output        i2c_we,
    output        kbd_we,
    output        mouse_we,
    output        disp_we,
    output        fb_we,
    output [31:0] prdata
);

// Device selection based on bits [11:8] of the address
wire [3:0] dev = pa[11:8];
wire fb_sel = (pa[19:18] == 2'b01);

 // Write enable signals
assign gpio_we = pw & (~fb_sel) & (dev == 4'b0000);
assign spi_we  = pw & (~fb_sel) & (dev == 4'b0001);
assign i2c_we  = pw & (~fb_sel) & (dev == 4'b0010);
assign kbd_we  = pw & (~fb_sel) & (dev == 4'b0011);
assign mouse_we= pw & (~fb_sel) & (dev == 4'b0100);
assign disp_we = pw & (~fb_sel) & (dev == 4'b0101);
assign fb_we   = pw & fb_sel;

// Read data multiplexer
assign prdata = fb_sel ? fb_rdata :
                (dev == 4'b0000) ? gpio_rdata :
                (dev == 4'b0001) ? spi_rdata  :
                (dev == 4'b0010) ? i2c_rdata  :
                (dev == 4'b0011) ? kbd_rdata  :
                (dev == 4'b0100) ? mouse_rdata :
                (dev == 4'b0101) ? disp_rdata :
                32'b0;

endmodule
