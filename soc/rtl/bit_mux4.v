module bit_mux4 (
    input  sel0,
    input  sel1,
    input  sel2,
    input  sel3,
    input  d0,
    input  d1,
    input  d2,
    input  d3,
    output y
);

    assign y = (sel0 & d0) | (sel1 & d1) | (sel2 & d2) | (sel3 & d3);

endmodule
