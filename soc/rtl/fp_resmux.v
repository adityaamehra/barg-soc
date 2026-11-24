module fp_resmux (
    input  wire [31:0] from_alu,
    input  wire [31:0] from_fp,
    input  wire        sel,
    output wire [31:0] y
);

    assign y = sel ? from_fp : from_alu;

endmodule
