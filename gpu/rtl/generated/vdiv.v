module vdiv (
    input clk,
    input rst,
    input clear,
    input valid,
    input [2:0] unit,
    input [1:0] md_op,
    input [127:0] a,
    input [127:0] b,
    input advance,
    output ready,
    output [127:0] y
);

localparam [1:0] ST_IDLE = 2'd0;
localparam [1:0] ST_BUSY = 2'd1;
localparam [1:0] ST_DONE = 2'd2;

reg [1:0] state;
reg [4:0] count;
reg [1:0] op;

wire start = valid && (unit == 3'b010);
wire md_signed = (md_op == 2'd0) || (md_op == 2'd2);

always @(posedge clk) begin
    if (rst || clear) begin
        state <= ST_IDLE;
        count <= 5'd0;
        op <= 2'd0;
    end else begin
        case (state)
            ST_IDLE: begin
                if (start) begin
                    op <= md_op;
                    count <= 5'd0;
                    state <= ST_BUSY;
                end
            end
            ST_BUSY: begin
                if (count == 5'd31)
                    state <= ST_DONE;
                else
                    count <= count + 5'd1;
            end
            ST_DONE: begin
                if (advance)
                    state <= ST_IDLE;
            end
            default: state <= ST_IDLE;
        endcase
    end
end

assign ready = (state == ST_DONE);

genvar i;
generate
    for (i = 0; i < 4; i = i + 1) begin : lanes
        wire [31:0] a_lane = a[32*i +: 32];
        wire [31:0] b_lane = b[32*i +: 32];
        wire [31:0] abs_a = a_lane[31] ? (~a_lane + 32'd1) : a_lane;
        wire [31:0] abs_b = b_lane[31] ? (~b_lane + 32'd1) : b_lane;

        reg [31:0] x_orig;
        reg [31:0] z_orig;
        reg [31:0] z_mag;
        reg [31:0] dividend;
        reg [31:0] quo;
        reg [32:0] rem;

        wire [32:0] rem_shift = {rem[31:0], dividend[31]};
        wire [32:0] z_ext = {1'b0, z_mag};
        wire [32:0] rem_sub = rem_shift - z_ext;
        wire [31:0] quo_neg = ~quo + 32'd1;
        wire [31:0] rem_neg = ~rem[31:0] + 32'd1;

        always @(posedge clk) begin
            if (rst || clear) begin
                x_orig <= 32'd0;
                z_orig <= 32'd0;
                z_mag <= 32'd0;
                dividend <= 32'd0;
                quo <= 32'd0;
                rem <= 33'd0;
            end else if (state == ST_IDLE && start) begin
                x_orig <= a_lane;
                z_orig <= b_lane;
                z_mag <= md_signed ? abs_b : b_lane;
                dividend <= md_signed ? abs_a : a_lane;
                quo <= 32'd0;
                rem <= 33'd0;
            end else if (state == ST_BUSY) begin
                dividend <= {dividend[30:0], 1'b0};
                if (rem_shift >= z_ext) begin
                    rem <= rem_sub;
                    quo <= {quo[30:0], 1'b1};
                end else begin
                    rem <= rem_shift;
                    quo <= {quo[30:0], 1'b0};
                end
            end
        end

        wire [31:0] lane_y;
        assign lane_y =
            (op == 2'd0) ? ((z_orig == 32'd0) ? 32'hFFFFFFFF :
                ((x_orig == 32'h80000000 && z_orig == 32'hFFFFFFFF) ? 32'h80000000 :
                    ((x_orig[31] ^ z_orig[31]) ? quo_neg : quo))) :
            (op == 2'd1) ? ((z_orig == 32'd0) ? 32'hFFFFFFFF : quo) :
            (op == 2'd2) ? ((z_orig == 32'd0) ? x_orig :
                ((x_orig == 32'h80000000 && z_orig == 32'hFFFFFFFF) ? 32'd0 :
                    (x_orig[31] ? rem_neg : rem[31:0]))) :
            ((z_orig == 32'd0) ? x_orig : rem[31:0]);

        assign y[32*i +: 32] = (state == ST_DONE) ? lane_y : 32'd0;
    end
endgenerate

endmodule
