module dfault_gate (
    input  wire access,
    input  wire xlate,
    input  wire pf,
    input  wire af,
    output wire pf_o,
    output wire af_o
);

    // Page fault output: active only when access and translation are enabled
    assign pf_o = pf & access & xlate;

    // Access fault output: active only when access and translation are enabled
    assign af_o = af & access & xlate;

endmodule
