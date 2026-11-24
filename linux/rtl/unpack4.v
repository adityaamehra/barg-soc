module unpack4(
    input  wire [127:0] bus128,
    output wire [31:0]  w0,
    output wire [31:0]  w1,
    output wire [31:0]  w2,
    output wire [31:0]  w3
);

    assign w0 = bus128[31:0];
    assign w1 = bus128[63:32];
    assign w2 = bus128[95:64];
    assign w3 = bus128[127:96];

endmodule
