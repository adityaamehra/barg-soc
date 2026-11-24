module gfx_sel (
    input gfx,
    input [127:0] alu_y,
    input [127:0] gfx_y,
    input [127:0] tex_y,
    input [127:0] z_y,
    output [127:0] y
);

    assign y = gfx ? (gfx_y | tex_y | z_y) : alu_y;

endmodule
