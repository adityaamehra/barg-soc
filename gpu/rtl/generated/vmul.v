module vmul (
    input  wire [127:0] a,
    input  wire [127:0] b,
    input  wire [1:0]   md_op,
    output wire [127:0] y
);
    genvar i;
    generate
        for (i = 0; i < 4; i = i + 1) begin : g_lane
            wire [31:0] x = a[32*i +: 32];
            wire [31:0] z = b[32*i +: 32];

            wire [63:0] p_ss = $signed({x[31], x}) * $signed({z[31], z});
            wire [63:0] p_su = $signed({x[31], x}) * $signed({1'b0, z});
            wire [63:0] p_uu = {1'b0, x} * {1'b0, z};

            reg [31:0] r;
            always @* begin
                case (md_op)
                    2'd0: r = p_ss[31:0];
                    2'd1: r = p_ss[63:32];
                    2'd2: r = p_su[63:32];
                    default: r = p_uu[63:32];
                endcase
            end

            assign y[32*i +: 32] = r;
        end
    endgenerate
endmodule
