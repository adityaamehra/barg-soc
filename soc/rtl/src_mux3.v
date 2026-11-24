module src_mux3 (
    input  wire [1:0]   src,
    input  wire [31:0]  a,
    input  wire [31:0]  b,
    input  wire [31:0]  c,
    output reg  [31:0]  y
);

    always @* begin
        case (src)
            2'b00: y = a;
            2'b01: y = b;
            2'b10: y = c;
            2'b11: y = 32'd0;
            default: y = 32'd0;
        endcase
    end

endmodule
