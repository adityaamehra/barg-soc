module need_hi_gen (
    input  wire [31:0] pc,
    input  wire [31:0] word_lo,
    output wire        need_hi
);

    assign need_hi = pc[1] & (word_lo[17:16] == 2'b11);

endmodule
