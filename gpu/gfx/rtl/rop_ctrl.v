module rop_ctrl (
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
    input  wire        tex_busy,
    output wire        g_busy,
    output wire        blend
);

    reg blend_r;
    reg pending;

    assign blend = blend_r;
    assign g_busy = tex_busy | (valid & gfx & (gfx_op == 3'd5) & blend_r & ~pending);

    integer l;
    reg cfg_hit;
    reg [31:0] lane_a;
    reg [31:0] lane_b;

    always @* begin
        cfg_hit = 1'b0;
        lane_a = 32'd0;
        lane_b = 32'd0;
        for (l = 0; l < 4; l = l + 1) begin
            if (!cfg_hit && tmask[l]) begin
                cfg_hit = 1'b1;
                lane_a = a[32*l +: 32];
                lane_b = b[32*l +: 32];
            end
        end
    end

    always @(posedge clk) begin
        if (rst | clear) begin
            blend_r <= 1'b0;
            pending <= 1'b0;
        end else begin
            if (advance)
                pending <= 1'b0;
            else if (valid & gfx & (gfx_op == 3'd5) & blend_r)
                pending <= 1'b1;

            if (valid & advance & gfx & (gfx_op == 3'd0) & (tmask != 4'd0) & cfg_hit
                & (lane_a == 32'd4))
                blend_r <= lane_b[0];
        end
    end

endmodule
