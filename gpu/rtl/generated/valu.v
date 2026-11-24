module valu (
    input  wire [127:0] a,
    input  wire [127:0] b,
    input  wire [31:0]  imm,
    input  wire [31:0]  pc,
    input  wire         a_sel,
    input  wire         b_sel,
    input  wire [3:0]   alu_op,
    input  wire [2:0]   br_op,
    output wire [127:0] y,
    output wire [3:0]   taken
);
    integer i;

    wire [31:0] x [0:3];
    wire [31:0] z [0:3];
    reg  [31:0] r [0:3];

    generate
        genvar g;
        for (g = 0; g < 4; g = g + 1) begin : lanes
            assign x[g] = a_sel ? pc : a[32*g +: 32];
            assign z[g] = b_sel ? imm : b[32*g +: 32];
        end
    endgenerate

    always @* begin
        for (i = 0; i < 4; i = i + 1) begin
            case (alu_op)
                4'b0000: r[i] = x[i] + z[i];
                4'b0001: r[i] = x[i] - z[i];
                4'b0010: r[i] = x[i] << z[i][4:0];
                4'b0011: r[i] = ($signed(x[i]) < $signed(z[i])) ? 32'd1 : 32'd0;
                4'b0100: r[i] = (x[i] < z[i]) ? 32'd1 : 32'd0;
                4'b0101: r[i] = x[i] ^ z[i];
                4'b0110: r[i] = x[i] >> z[i][4:0];
                4'b0111: r[i] = $signed(x[i]) >>> z[i][4:0];
                4'b1000: r[i] = x[i] | z[i];
                4'b1001: r[i] = x[i] & z[i];
                4'b1010: r[i] = z[i];
                default: r[i] = 32'd0;
            endcase
        end
    end

    assign y = {r[3], r[2], r[1], r[0]};

    reg [3:0] t;
    always @* begin
        t = 4'b0000;
        for (i = 0; i < 4; i = i + 1) begin
            case (br_op)
                3'b000: t[i] = (a[32*i +: 32] == b[32*i +: 32]);
                3'b001: t[i] = (a[32*i +: 32] != b[32*i +: 32]);
                3'b010: t[i] = 1'b0;
                3'b011: t[i] = 1'b0;
                3'b100: t[i] = $signed(a[32*i +: 32]) < $signed(b[32*i +: 32]);
                3'b101: t[i] = $signed(a[32*i +: 32]) >= $signed(b[32*i +: 32]);
                3'b110: t[i] = (a[32*i +: 32] < b[32*i +: 32]);
                3'b111: t[i] = (a[32*i +: 32] >= b[32*i +: 32]);
            endcase
        end
    end
    assign taken = t;

endmodule
