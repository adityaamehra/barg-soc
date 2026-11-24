module vote_shfl (
    input  [2:0]  simt_op,
    input  [1:0]  simt_mode,
    input  [3:0]  tmask,
    input  [127:0] a,
    input  [127:0] b,
    output [127:0] y
);

    integer l;
    reg [31:0] lane_y [0:3];
    reg [127:0] y_r;

    // ballot: active lanes whose lane of a is nonzero
    wire [3:0] nz;
    assign nz[0] = tmask[0] & (a[31:0]    != 32'd0);
    assign nz[1] = tmask[1] & (a[63:32]   != 32'd0);
    assign nz[2] = tmask[2] & (a[95:64]   != 32'd0);
    assign nz[3] = tmask[3] & (a[127:96]  != 32'd0);

    wire [3:0] ballot = nz;

    // vote result value
    reg [31:0] vote_val;
    always @* begin
        case (simt_mode)
            2'd0: vote_val = (ballot != 4'd0) ? 32'd1 : 32'd0;
            2'd1: vote_val = (ballot == tmask) ? 32'd1 : 32'd0;
            2'd2: vote_val = {28'd0, ballot};
            default: vote_val = 32'd0;
        endcase
    end

    // shuffle source lane per destination lane
    reg [1:0] s0, s1, s2, s3;
    wire [31:0] k0 = b[31:0];
    wire [31:0] k1 = b[63:32];
    wire [31:0] k2 = b[95:64];
    wire [31:0] k3 = b[127:96];

    // 3-bit arithmetic so the >= 4 / > l checks are real comparisons
    wire [2:0] big0 = {1'b0, k0[1:0]};
    wire [2:0] big1 = {1'b0, k1[1:0]};
    wire [2:0] big2 = {1'b0, k2[1:0]};
    wire [2:0] big3 = {1'b0, k3[1:0]};

    always @* begin
        case (simt_mode)
            2'd0: begin // idx: s = k mod 4
                s0 = k0[1:0];
                s1 = k1[1:0];
                s2 = k2[1:0];
                s3 = k3[1:0];
            end
            2'd1: begin // xor: s = (l xor k) mod 4
                s0 = 2'd0 ^ k0[1:0];
                s1 = 2'd1 ^ k1[1:0];
                s2 = 2'd2 ^ k2[1:0];
                s3 = 2'd3 ^ k3[1:0];
            end
            2'd2: begin // up: s = l - k, or l if k > l (k >= 4 or k > l)
                s0 = ((k0[31:2] != 30'd0) || (big0 > 3'd0)) ? 2'd0 : (2'd0 - k0[1:0]);
                s1 = ((k1[31:2] != 30'd0) || (big1 > 3'd1)) ? 2'd1 : (2'd1 - k1[1:0]);
                s2 = ((k2[31:2] != 30'd0) || (big2 > 3'd2)) ? 2'd2 : (2'd2 - k2[1:0]);
                s3 = ((k3[31:2] != 30'd0) || (big3 > 3'd3)) ? 2'd3 : (2'd3 - k3[1:0]);
            end
            default: begin // down: s = l + k, or l if l + k >= 4
                s0 = ((k0[31:2] != 30'd0) || ((3'd0 + big0) >= 3'd4)) ? 2'd0 : (2'd0 + k0[1:0]);
                s1 = ((k1[31:2] != 30'd0) || ((3'd1 + big1) >= 3'd4)) ? 2'd1 : (2'd1 + k1[1:0]);
                s2 = ((k2[31:2] != 30'd0) || ((3'd2 + big2) >= 3'd4)) ? 2'd2 : (2'd2 + k2[1:0]);
                s3 = ((k3[31:2] != 30'd0) || ((3'd3 + big3) >= 3'd4)) ? 2'd3 : (2'd3 + k3[1:0]);
            end
        endcase
    end

    always @* begin
        for (l = 0; l < 4; l = l + 1)
            lane_y[l] = 32'd0;
        case (simt_op)
            3'b101: begin // VOTE
                lane_y[0] = vote_val;
                lane_y[1] = vote_val;
                lane_y[2] = vote_val;
                lane_y[3] = vote_val;
            end
            3'b110: begin // SHFL
                lane_y[0] = a[s0*32 +: 32];
                lane_y[1] = a[s1*32 +: 32];
                lane_y[2] = a[s2*32 +: 32];
                lane_y[3] = a[s3*32 +: 32];
            end
            default: begin
                lane_y[0] = 32'd0;
                lane_y[1] = 32'd0;
                lane_y[2] = 32'd0;
                lane_y[3] = 32'd0;
            end
        endcase
    end

    assign y = {lane_y[3], lane_y[2], lane_y[1], lane_y[0]};

endmodule
