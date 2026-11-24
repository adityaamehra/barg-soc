module word_addr24 (
    input  wire [31:0] addr,
    output wire [23:0] word
);

    assign word = addr[25:2];

endmodule
