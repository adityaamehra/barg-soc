module tex_ctrl (
    input  wire        clk,
    input  wire        rst,
    input  wire        clear,
    input  wire        valid,
    input  wire        advance,
    input  wire        gfx,
    input  wire [2:0]  gfx_op,
    input  wire [3:0]  tmask,
    input  wire [127:0] a,
    input  wire [127:0] b,
    output wire        g_busy,
    output reg  [2:0]  tex_mode
);

    reg pending;

    wire is_tex = valid & gfx & (gfx_op == 3'd4);

    assign g_busy = is_tex & ~pending;

    wire [1:0] cfg_lane = tmask[0] ? 2'd0 :
                          tmask[1] ? 2'd1 :
                          tmask[2] ? 2'd2 : 2'd3;
    wire       cfg_en   = valid & advance & gfx & (gfx_op == 3'd0) & (tmask != 4'b0000);
    wire [2:0] cfg_val  = tmask[0] ? b[2:0] :
                          tmask[1] ? b[34:32] :
                          tmask[2] ? b[66:64] : b[98:96];

    always @(posedge clk) begin
        if (rst | clear) begin
            pending  <= 1'b0;
            tex_mode <= 3'b000;
        end else begin
            if (advance)
                pending <= 1'b0;
            else if (is_tex)
                pending <= 1'b1;

            if (cfg_en & (a[cfg_lane*32 +: 32] == 32'd32))
                tex_mode <= cfg_val;
        end
    end

endmodule
