module word_addr(
    input  [31:0] addr,
    output [21:0] word
);

    assign word = addr[23:2];

endmodule
