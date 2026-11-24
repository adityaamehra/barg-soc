module z_ctrl (
    input  wire       clk,
    input  wire       rst,
    input  wire       clear,
    input  wire       valid,
    input  wire       advance,
    input  wire       gfx,
    input  wire [2:0] gfx_op,
    input  wire       in_busy,
    output wire       g_busy
);

    reg pending;

    assign g_busy = in_busy | (valid & gfx & (gfx_op == 3'd6) & !pending);

    always @(posedge clk) begin
        if (rst | clear)
            pending <= 1'b0;
        else if (advance)
            pending <= 1'b0;
        else if (valid & gfx & (gfx_op == 3'd6))
            pending <= 1'b1;
    end

endmodule
