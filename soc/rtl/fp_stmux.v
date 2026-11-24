module fp_stmux (
    input  wire [31:0] from_core,
    input  wire [63:0] fdata,
    input  wire        is_fst,
    input  wire [1:0]  dwsel,
    output wire [31:0] y
);

    assign y = is_fst ? (dwsel == 2'b10 ? fdata[63:32] : fdata[31:0]) : from_core;

endmodule
