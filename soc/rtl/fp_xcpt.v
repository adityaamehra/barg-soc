module fp_xcpt (
    input  wire        xcpt_in,
    input  wire [3:0]  cause_in,
    input  wire [31:0] tval_in,
    input  wire        memwrite_in,
    input  wire        is_store,
    input  wire [1:0]  dwsel,
    input  wire [31:0] addr,
    output wire        xcpt,
    output wire [3:0]  cause,
    output wire [31:0] tval,
    output wire        memwrite_out
);

    wire bad = ~xcpt_in & (dwsel == 2'b01) & (addr[2:0] != 3'b000);

    assign xcpt         = xcpt_in | bad;
    assign cause        = bad ? (is_store ? 4'd6 : 4'd4) : cause_in;
    assign tval         = bad ? addr : tval_in;
    assign memwrite_out = memwrite_in & ~bad;

endmodule
