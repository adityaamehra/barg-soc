module unpack16 (
    input  wire [511:0] bus512,
    output wire [31:0] w0,
    output wire [31:0] w1,
    output wire [31:0] w2,
    output wire [31:0] w3,
    output wire [31:0] w4,
    output wire [31:0] w5,
    output wire [31:0] w6,
    output wire [31:0] w7,
    output wire [31:0] w8,
    output wire [31:0] w9,
    output wire [31:0] w10,
    output wire [31:0] w11,
    output wire [31:0] w12,
    output wire [31:0] w13,
    output wire [31:0] w14,
    output wire [31:0] w15
);

    assign w0  = bus512[31:0];
    assign w1  = bus512[63:32];
    assign w2  = bus512[95:64];
    assign w3  = bus512[127:96];
    assign w4  = bus512[159:128];
    assign w5  = bus512[191:160];
    assign w6  = bus512[223:192];
    assign w7  = bus512[255:224];
    assign w8  = bus512[287:256];
    assign w9  = bus512[319:288];
    assign w10 = bus512[351:320];
    assign w11 = bus512[383:352];
    assign w12 = bus512[415:384];
    assign w13 = bus512[447:416];
    assign w14 = bus512[479:448];
    assign w15 = bus512[511:480];

endmodule
