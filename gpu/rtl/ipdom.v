module ipdom (
    input  wire        clk,
    input  wire        rst,
    input  wire        clear_all,
    input  wire [1:0]  wid,
    input  wire        en,
    input  wire [1:0]  push,
    input  wire [3:0]  e0_mask,
    input  wire [31:0] e0_pc,
    input  wire        e0_fall,
    input  wire [3:0]  e1_mask,
    input  wire [31:0] e1_pc,
    input  wire        e1_fall,
    input  wire        pop,
    input  wire        clear,
    output wire [3:0]  depth,
    output wire [3:0]  top_mask,
    output wire [31:0] top_pc,
    output wire        top_fall
);

    reg [3:0]  mask_mem [0:3][0:7];
    reg [31:0] pc_mem   [0:3][0:7];
    reg        fall_mem [0:3][0:7];
    reg [3:0]  cnt      [0:3];

    integer i, j;
    initial begin
        for (i = 0; i < 4; i = i + 1) begin
            cnt[i] = 4'd0;
            for (j = 0; j < 8; j = j + 1) begin
                mask_mem[i][j] = 4'd0;
                pc_mem[i][j]   = 32'd0;
                fall_mem[i][j] = 1'b0;
            end
        end
    end

     wire [1:0] w = wid;

    always @(posedge clk) begin
        if (rst || clear_all) begin
            for (i = 0; i < 4; i = i + 1)
                cnt[i] <= 4'd0;
        end else if (en) begin
            if (clear) begin
                cnt[w] <= 4'd0;
            end else if (pop) begin
                if (cnt[w] != 4'd0)
                    cnt[w] <= cnt[w] - 4'd1;
             end else if (push == 2'd1) begin
                if (cnt[w] < 4'd8) begin
                    mask_mem[w][cnt[w]] <= e0_mask;
                    pc_mem[w][cnt[w]]   <= e0_pc;
                    fall_mem[w][cnt[w]] <= e0_fall;
                    cnt[w]              <= cnt[w] + 4'd1;
                end
             end else if (push == 2'd2) begin
                if (cnt[w] < 4'd8) begin
                    mask_mem[w][cnt[w]] <= e0_mask;
                    pc_mem[w][cnt[w]]   <= e0_pc;
                    fall_mem[w][cnt[w]] <= e0_fall;
                    if (cnt[w] + 4'd1 < 4'd8) begin
                        mask_mem[w][cnt[w]+4'd1] <= e1_mask;
                        pc_mem[w][cnt[w]+4'd1]   <= e1_pc;
                        fall_mem[w][cnt[w]+4'd1] <= e1_fall;
                        cnt[w] <= cnt[w] + 4'd2;
                    end else begin
                        cnt[w] <= cnt[w] + 4'd1;
                    end
                end
            end
        end
    end

     assign depth    = cnt[w][3:0];
    assign top_mask = (cnt[w] == 4'd0) ? 4'd0 : mask_mem[w][cnt[w]-4'd1];
    assign top_pc   = (cnt[w] == 4'd0) ? 32'd0 : pc_mem[w][cnt[w]-4'd1];
    assign top_fall = (cnt[w] == 4'd0) ? 1'b0 : fall_mem[w][cnt[w]-4'd1];

endmodule
