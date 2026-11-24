module kill_gate (
    input  wire        regwrite,
    input  wire        memwrite,
    input  wire        kill_wb,
    input  wire        kill_mem,
    output wire        regwrite_out,
    output wire        memwrite_out
);

    assign regwrite_out = regwrite & ~kill_wb;
    assign memwrite_out = memwrite & ~kill_mem;

endmodule
