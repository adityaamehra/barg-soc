module pack4(
    input  [21:0] a0,
    input  [21:0] a1,
    input  [21:0] a2,
    input  [21:0] a3,
    output [87:0] bus88
);

    assign bus88 = {a3, a2, a1, a0};

endmodule
