module fencei_gate (
    input  wire        valid,
    input  wire [2:0]  csrop,
    input  wire        trap_m,
    input  wire        trap_s,
    output wire        fence_i
);

    assign fence_i = valid & (csrop == 3'b111) & ~trap_m & ~trap_s;

endmodule
