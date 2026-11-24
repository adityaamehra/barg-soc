module simt_ctrl (
    input  wire        valid,
    input  wire [2:0]  unit,
    input  wire        advance,
    input  wire [2:0]  simt_op,
    input  wire [3:0]  tmask,
    input  wire [31:0] pc,
    input  wire [31:0] br_next_pc,
    input  wire [127:0] a,
    input  wire [127:0] b,
    input  wire [3:0]  top_mask,
    input  wire [31:0] top_pc,
    input  wire        top_fall,
    input  wire [3:0]  depth,
    output wire [31:0] c_pc,
    output wire [3:0]  c_tmask,
    output wire [1:0]  push,
    output wire [3:0]  e0_mask,
    output wire [31:0] e0_pc,
    output wire        e0_fall,
    output wire [3:0]  e1_mask,
    output wire [31:0] e1_pc,
    output wire        e1_fall,
    output wire        pop,
    output wire        clear,
    output wire [3:0]  spawn_mask,
    output wire [31:0] spawn_pc,
    output wire        bar_arrive,
    output wire [1:0]  bar_id,
    output wire [2:0]  bar_count,
    output wire        err
);

    // lowest-numbered active lane
    wire l0 = tmask[0] | (tmask == 4'b0000);        // lane 0 when no lane is active
    wire l1 = ~tmask[0] & tmask[1];
    wire l2 = ~tmask[0] & ~tmask[1] & tmask[2];
    wire l3 = ~tmask[0] & ~tmask[1] & ~tmask[2] & tmask[3];

    wire [31:0] fa = l0 ? a[31:0]   :
                     l1 ? a[63:32]  :
                     l2 ? a[95:64]  :
                          a[127:96];
    wire [31:0] fb = l0 ? b[31:0]   :
                     l1 ? b[63:32]  :
                     l2 ? b[95:64]  :
                          b[127:96];

    wire [31:0] p4 = pc + 32'd4;
    wire        is_simt = valid & (unit == 3'b100);

    // split predicate
    wire [3:0] pred = {a[127:96] != 32'd0, a[95:64] != 32'd0,
                       a[63:32]  != 32'd0, a[31:0]  != 32'd0};
    wire [3:0] sp_T = tmask & pred;
    wire [3:0] sp_F = tmask & ~pred;
    wire       t_nonz = |sp_T;
    wire       f_nonz = |sp_F;
    wire [1:0] sp_n   = (t_nonz & f_nonz) ? 2'd2 : 2'd1;
    wire       sp_ovf = (depth + {2'd0, sp_n}) > 4'd8;

    reg [31:0] c_pc_r;
    reg [3:0]  c_tmask_r;
    reg [1:0]  push_r;
    reg [3:0]  e0_mask_r;
    reg [31:0] e0_pc_r;
    reg        e0_fall_r;
    reg [3:0]  e1_mask_r;
    reg [31:0] e1_pc_r;
    reg        e1_fall_r;
    reg        pop_r;
    reg        clear_r;
    reg [3:0]  spawn_mask_r;
    reg [31:0] spawn_pc_r;
    reg        bar_arrive_r;
    reg [1:0]  bar_id_r;
    reg [2:0]  bar_count_r;
    reg        err_r;

    always @* begin
        c_pc_r       = br_next_pc;
        c_tmask_r    = tmask;
        push_r       = 2'd0;
        e0_mask_r    = 4'd0;
        e0_pc_r      = 32'd0;
        e0_fall_r    = 1'b0;
        e1_mask_r    = 4'd0;
        e1_pc_r      = 32'd0;
        e1_fall_r    = 1'b0;
        pop_r        = 1'b0;
        clear_r      = 1'b0;
        spawn_mask_r = 4'd0;
        spawn_pc_r   = 32'd0;
        bar_arrive_r = 1'b0;
        bar_id_r     = 2'd0;
        bar_count_r  = 3'd0;
        err_r        = 1'b0;

        if (is_simt) begin
            c_pc_r = p4;
            case (simt_op)
                3'b000: begin // TMC
                    c_tmask_r = fa[3:0];
                    clear_r   = (fa[3:0] == 4'd0);
                end
                3'b001: begin // WSPAWN
                    spawn_mask_r[3] = (32'd3 < fa);
                    spawn_mask_r[2] = (32'd2 < fa);
                    spawn_mask_r[1] = (32'd1 < fa);
                    spawn_mask_r[0] = 1'b0;
                    spawn_pc_r      = fb;
                end
                3'b010: begin // SPLIT
                    if (sp_ovf) begin
                        err_r = 1'b1;
                    end else begin
                        push_r    = sp_n;
                        e0_mask_r = tmask;
                        e0_pc_r   = 32'd0;
                        e0_fall_r = 1'b1;
                        if (sp_n == 2'd2) begin
                            e1_mask_r = sp_F;
                            e1_pc_r   = p4;
                            e1_fall_r = 1'b0;
                            c_tmask_r = sp_T;
                        end
                    end
                end
                3'b011: begin // JOIN
                    if (depth == 4'd0) begin
                        err_r = 1'b1;
                    end else begin
                        pop_r     = 1'b1;
                        c_tmask_r = top_mask;
                        c_pc_r    = top_fall ? p4 : top_pc;
                    end
                end
                3'b100: begin // BAR
                    bar_arrive_r = 1'b1;
                    bar_id_r     = fa[1:0];
                    bar_count_r  = (fb < 32'd7) ? fb[2:0] : 3'd7;
                    err_r        = (fa > 32'd3);
                end
                3'b101: begin // VOTE
                end
                3'b110: begin // SHFL
                end
                default: begin // 111
                end
            endcase
        end
    end

    assign c_pc       = c_pc_r;
    assign c_tmask    = c_tmask_r;
    assign push       = advance ? push_r : 2'd0;
    assign e0_mask    = e0_mask_r;
    assign e0_pc      = e0_pc_r;
    assign e0_fall    = e0_fall_r;
    assign e1_mask    = e1_mask_r;
    assign e1_pc      = e1_pc_r;
    assign e1_fall    = e1_fall_r;
    assign pop        = advance ? pop_r : 1'b0;
    assign clear      = advance ? clear_r : 1'b0;
    assign spawn_mask = advance ? spawn_mask_r : 4'd0;
    assign spawn_pc   = spawn_pc_r;
    assign bar_arrive = advance ? bar_arrive_r : 1'b0;
    assign bar_id     = bar_id_r;
    assign bar_count  = bar_count_r;
    assign err        = err_r;

endmodule
