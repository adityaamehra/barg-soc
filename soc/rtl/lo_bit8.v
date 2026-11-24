module lo_bit8 (
    input  wire [7:0] y,
    output wire       b0
);

    assign b0 = y[0];

endmodule
