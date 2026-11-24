module raster_eval (
    input  wire        gfx,
    input  wire [2:0]  gfx_op,
    input  wire [127:0] a,
    input  wire [127:0] b,
    input  wire [9:0]  s_x,
    input  wire [9:0]  s_y,
    input  wire        s_done,
    input  wire [31:0] ea0,
    input  wire [31:0] eb0,
    input  wire [31:0] ec0,
    input  wire [31:0] ea1,
    input  wire [31:0] eb1,
    input  wire [31:0] ec1,
    input  wire [31:0] ea2,
    input  wire [31:0] eb2,
    input  wire [31:0] ec2,
    input  wire [2:0]  bias,
    output wire [127:0] y
);
    genvar l;
    generate
        for (l = 0; l < 4; l = l + 1) begin : g_lane
            // rast.edge inputs
            wire [31:0] p  = a[32*l +: 32];
            wire [31:0] nb = b[32*l +: 32];
            wire [15:0] px = p[15:0];
            wire [15:0] py = p[31:16];
            wire [1:0]  n  = nb[1:0];

            // edge evaluation for rast.edge
            wire [31:0] e0 = ea0 * {16'd0, px} + eb0 * {16'd0, py} + ec0;
            wire [31:0] e1 = ea1 * {16'd0, px} + eb1 * {16'd0, py} + ec1;
            wire [31:0] e2 = ea2 * {16'd0, px} + eb2 * {16'd0, py} + ec2;
            reg [31:0] eval_e;
            always @* begin
                case (n)
                    2'd0: eval_e = e0;
                    2'd1: eval_e = e1;
                    2'd2: eval_e = e2;
                    default: eval_e = 32'd0;
                endcase
            end

            // rast coverage
            wire [9:0]  xl = s_x + l[9:0];
            wire [31:0] c0 = ea0 * {22'd0, xl} + eb0 * {22'd0, s_y} + ec0;
            wire [31:0] c1 = ea1 * {22'd0, xl} + eb1 * {22'd0, s_y} + ec1;
            wire [31:0] c2 = ea2 * {22'd0, xl} + eb2 * {22'd0, s_y} + ec2;
            wire signed [31:0] t0 = $signed(c0) + $signed({31'd0, bias[0]});
            wire signed [31:0] t1 = $signed(c1) + $signed({31'd0, bias[1]});
            wire signed [31:0] t2 = $signed(c2) + $signed({31'd0, bias[2]});
            wire covered = (t0 > 32'sd0) && (t1 > 32'sd0) && (t2 > 32'sd0);
            wire [31:0] rast_val = covered ? {6'd0, s_y, 6'd0, xl}
                                           : {16'hFFFF, 6'd0, xl};

            reg [31:0] lane;
            always @* begin
                if (!gfx)
                    lane = 32'd0;
                else if (gfx_op == 3'd1)
                    lane = s_done ? 32'hFFFFFFFF : rast_val;
                else if (gfx_op == 3'd3)
                    lane = eval_e;
                else
                    lane = 32'd0;
            end

            assign y[32*l +: 32] = lane;
        end
    endgenerate
endmodule
