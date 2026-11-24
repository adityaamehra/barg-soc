module split2 (
    input  wire [1:0] y,
    output wire       b0,
    output wire       b1
);

    assign b0 = y[0];
    assign b1 = y[1];

endmodule
