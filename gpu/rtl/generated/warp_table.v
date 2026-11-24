module warp_table (
    input  wire        clk,
    input  wire        rst,
    input  wire        start,
    input  wire [31:0] start_pc,
    input  wire        fire,
    input  wire [1:0]  fwid,
    input  wire        commit,
    input  wire [1:0]  cwid,
    input  wire [31:0] c_pc,
    input  wire [3:0]  c_tmask,
    input  wire [3:0]  spawn_mask,
    input  wire [31:0] spawn_pc,
    output wire [31:0] sel_pc,
    output wire [3:0]  sel_tmask,
    output wire [3:0]  active,
    output wire [3:0]  inflight,
    output wire        busy
);

    reg [31:0] pc  [0:3];
    reg [3:0]  tmask [0:3];
    reg [3:0]  infl;

    assign inflight = infl;
    // active bit w = (tmask[w] != 0)
    wire [3:0] act;
    assign act[0] = (tmask[0] != 4'b0000);
    assign act[1] = (tmask[1] != 4'b0000);
    assign act[2] = (tmask[2] != 4'b0000);
    assign act[3] = (tmask[3] != 4'b0000);
    assign active = act;

    assign busy = (act != 4'b0000) | (infl != 4'b0000);

    assign sel_pc    = pc[fwid];
    assign sel_tmask = tmask[fwid];

    // spawn condition per warp, from values before this edge
    wire [3:0] spawn_hit;
    assign spawn_hit[0] = spawn_mask[0] & (tmask[0] == 4'b0000) & ~infl[0];
    assign spawn_hit[1] = spawn_mask[1] & (tmask[1] == 4'b0000) & ~infl[1];
    assign spawn_hit[2] = spawn_mask[2] & (tmask[2] == 4'b0000) & ~infl[2];
    assign spawn_hit[3] = spawn_mask[3] & (tmask[3] == 4'b0000) & ~infl[3];

    integer w;
    always @(posedge clk) begin
        if (rst) begin
            pc[0] <= 32'd0; pc[1] <= 32'd0; pc[2] <= 32'd0; pc[3] <= 32'd0;
            tmask[0] <= 4'b0000; tmask[1] <= 4'b0000;
            tmask[2] <= 4'b0000; tmask[3] <= 4'b0000;
            infl <= 4'b0000;
        end else if (start) begin
            pc[0] <= start_pc;
            tmask[0] <= 4'b0001;
            pc[1] <= 32'd0; pc[2] <= 32'd0; pc[3] <= 32'd0;
            tmask[1] <= 4'b0000; tmask[2] <= 4'b0000; tmask[3] <= 4'b0000;
            infl <= 4'b0000;
        end else begin
            for (w = 0; w < 4; w = w + 1) begin
                // default: hold
                pc[w]   <= pc[w];
                tmask[w] <= tmask[w];
                // commit
                if (commit && (cwid == w[1:0])) begin
                    pc[w]   <= c_pc;
                    tmask[w] <= c_tmask;
                    infl[w] <= 1'b0;
                end
                // fire (in-flight only; does not touch pc/mask)
                if (fire && (fwid == w[1:0])) begin
                    infl[w] <= 1'b1;
                end
                // spawn overrides commit pc/mask
                if (spawn_hit[w]) begin
                    pc[w]   <= spawn_pc;
                    tmask[w] <= 4'b0001;
                end
            end
        end
    end

endmodule
