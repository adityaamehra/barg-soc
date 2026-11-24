module vga_timing(
    input  clk,
    input  rst,
    input  enable,
    output de,
    output hs,
    output vs,
    output vbl,
    output frame,
    output [15:0] widx,
    output half
);

    // Registers
    reg [1:0] div;
    reg [9:0] hc;
    reg [9:0] vc;

    // Sequential logic
    always @(posedge clk) begin
        if (rst) begin
            div <= 2'b00;
            hc  <= 10'b0;
            vc  <= 10'b0;
        end else begin
            div <= div + 1'b1;
            if (div == 2'b11) begin
                if (hc == 10'd799) begin
                    hc <= 10'd0;
                    if (vc == 10'd524)
                        vc <= 10'd0;
                    else
                        vc <= vc + 1'b1;
                end else begin
                    hc <= hc + 1'b1;
                end
            end
        end
    end

    // Combinational outputs
    wire active;
    assign active = (hc < 10'd640) & (vc < 10'd480);
    assign de     = active & enable;
    assign hs     = (hc < 10'd656) | (hc > 10'd751);
    assign vs     = (vc != 10'd490) & (vc != 10'd491);
    assign vbl    = (vc >= 10'd480);
    assign frame  = (div == 2'b11) & (hc == 10'd799) & (vc == 10'd524);
    assign widx   = (( {6'd0, vc} >> 1) * 8'd160 + ( {6'd0, hc} >> 2));
    assign half   = hc[1];

endmodule
