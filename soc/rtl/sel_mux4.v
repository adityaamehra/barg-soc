module sel_mux4 (
    input  wire        sel0,
    input  wire        sel1,
    input  wire        sel2,
    input  wire        sel3,
    input  wire [31:0] d0,
    input  wire [31:0] d1,
    input  wire [31:0] d2,
    input  wire [31:0] d3,
    output wire [31:0] y
);

    assign y = (d0 & {32{sel0}}) |
               (d1 & {32{sel1}}) |
               (d2 & {32{sel2}}) |
               (d3 & {32{sel3}});

endmodule
