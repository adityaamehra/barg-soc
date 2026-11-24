module pack16 (
    input  wire [21:0] a0,
    input  wire [21:0] a1,
    input  wire [21:0] a2,
    input  wire [21:0] a3,
    input  wire [21:0] a4,
    input  wire [21:0] a5,
    input  wire [21:0] a6,
    input  wire [21:0] a7,
    input  wire [21:0] a8,
    input  wire [21:0] a9,
    input  wire [21:0] a10,
    input  wire [21:0] a11,
    input  wire [21:0] a12,
    input  wire [21:0] a13,
    input  wire [21:0] a14,
    input  wire [21:0] a15,
    output wire [351:0] bus352
);

    assign bus352 = {a15, a14, a13, a12, a11, a10, a9, a8, a7, a6, a5, a4, a3, a2, a1, a0};

endmodule
