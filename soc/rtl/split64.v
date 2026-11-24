module split64 (
    input  [63:0] y,
    output [31:0] lo,
    output [31:0] hi
);

    assign lo = y[31:0];
    assign hi = y[63:32];

endmodule
