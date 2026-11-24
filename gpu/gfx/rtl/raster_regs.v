module raster_regs (
    input  wire         clk,
    input  wire         rst,
    input  wire         clear,
    input  wire         valid,
    input  wire         advance,
    input  wire         gfx,
    input  wire  [2:0]  gfx_op,
    input  wire  [3:0]  tmask,
    input  wire  [1:0]  wid,
    input  wire  [127:0] a,
    input  wire  [127:0] b,
    output wire  [31:0] ea0,
    output wire  [31:0] eb0,
    output wire  [31:0] ec0,
    output wire  [31:0] ea1,
    output wire  [31:0] eb1,
    output wire  [31:0] ec1,
    output wire  [31:0] ea2,
    output wire  [31:0] eb2,
    output wire  [31:0] ec2,
    output wire  [2:0]  bias,
    output wire  [9:0]  s_x,
    output wire  [9:0]  s_y,
    output wire         s_done
);

    reg [8:0]  x0, y0, x1, y1;
    reg [31:0] coef [0:8];
    reg [2:0]  bias_r;
    reg [9:0]  sx  [0:3];
    reg [9:0]  sy  [0:3];
    reg        sdone [0:3];

    assign ea0 = coef[0];
    assign eb0 = coef[1];
    assign ec0 = coef[2];
    assign ea1 = coef[3];
    assign eb1 = coef[4];
    assign ec1 = coef[5];
    assign ea2 = coef[6];
    assign eb2 = coef[7];
    assign ec2 = coef[8];
    assign bias = bias_r;

    assign s_x    = sx[wid];
    assign s_y    = sy[wid];
    assign s_done = sdone[wid];

    wire en = valid & advance & gfx & (tmask != 4'b0000);

    // lowest set lane of tmask
    integer l;
    always @* begin
        if (tmask[0])      l = 0;
        else if (tmask[1]) l = 1;
        else if (tmask[2]) l = 2;
        else               l = 3;
    end

    wire [31:0] n = a[l*32 +: 32];
    wire [31:0] v = b[l*32 +: 32];

    wire [8:0] v_x0 = v[8:0] & 9'h1FC; // bits 8:0 with bits 1:0 cleared
    wire [8:0] v_y0 = v[24:16];
    wire [8:0] v_x1 = v[8:0];
    wire [8:0] v_y1 = v[24:16];

    wire [9:0] nx = {v_x0[8:2], 2'b00};
    wire [9:0] ny = {2'b00, v_y0};
    wire [1:0] q  = ny[1:0];

    // rast step for warp wid
    wire        d0   = sdone[wid];
    wire [9:0]  sxw  = sx[wid];
    wire [9:0]  syw  = sy[wid];
    wire        wrap = (sxw + 10'd4) > {2'b00, x1};
    wire [9:0]  nsx  = wrap ? {2'b00, x0} : sxw + 10'd4;
    wire [9:0]  nsy  = wrap ? syw + 10'd4 : syw;
    wire        ndone = wrap ? ((syw + 10'd4) > {2'b00, y1}) : 1'b0;

    integer w;
    reg [9:0] rsy [0:3];
    reg       rdn [0:3];

    always @(posedge clk) begin
        if (rst | clear) begin
            x0 <= 9'd0; y0 <= 9'd0; x1 <= 9'd0; y1 <= 9'd0;
            bias_r <= 3'd0;
            for (w = 0; w < 9; w = w + 1)
                coef[w] <= 32'd0;
            for (w = 0; w < 4; w = w + 1) begin
                sx[w]    <= 10'd0;
                sy[w]    <= 10'd0;
                sdone[w] <= 1'b1;
            end
        end else if (en) begin
            if (gfx_op == 3'd0) begin
                case (n)
                    32'd8: begin
                        x0 <= v_x0;
                        y0 <= v_y0;
                        for (w = 0; w < 4; w = w + 1) begin
                            sx[w] <= nx;
                            sy[w] <= rsy[w];
                            sdone[w] <= rdn[w];
                        end
                    end
                    32'd9: begin
                        x1 <= v_x1;
                        y1 <= v_y1;
                    end
                    32'd16: coef[0] <= v;
                    32'd17: coef[1] <= v;
                    32'd18: coef[2] <= v;
                    32'd19: coef[3] <= v;
                    32'd20: coef[4] <= v;
                    32'd21: coef[5] <= v;
                    32'd22: coef[6] <= v;
                    32'd23: coef[7] <= v;
                    32'd24: coef[8] <= v;
                    32'd25: bias_r <= v[2:0];
                    default: ;
                endcase
            end else if (gfx_op == 3'd1) begin
                if (!d0) begin
                    sx[wid]    <= nsx;
                    sy[wid]    <= nsy;
                    sdone[wid] <= ndone;
                end
            end
        end
    end

    // compute restart scan values combinationally
    always @* begin
        for (w = 0; w < 4; w = w + 1) begin
            rsy[w] = ny - {8'd0, q} + w[9:0];
            if (w < q)
                rsy[w] = rsy[w] + 10'd4;
            rdn[w] = (rsy[w] > {2'b00, y1}) || (nx > {2'b00, x1});
        end
    end

endmodule
