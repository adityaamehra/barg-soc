module gshare_tbl (
    input clk,
    input rst,
    input [31:0] pc,
    input stall,
    input upd_en,
    input [7:0] upd_idx,
    input upd_taken,
    input upd_cond,
    input upd_jump,
    input [31:0] upd_pc,
    input [31:0] upd_target,
    output pred_taken,
    output pred_redirect,
    output [31:0] pred_target,
    output [7:0] pred_idx
);
    reg [7:0] ghr;
    reg [1:0] pht [0:255];
    reg btb_valid [0:31];
    reg [25:0] btb_tag [0:31];
    reg [31:0] btb_target [0:31];
    reg btb_jump [0:31];

    wire [7:0] idx;
    wire [4:0] bi;
    wire [25:0] lookup_tag;
    wire [1:0] pht_sel;
    wire hit;

    integer i;

    assign idx = pc[8:1] ^ ghr;
    assign bi = pc[5:1];
    assign lookup_tag = pc[31:6];
    assign pht_sel = pht[idx];
    assign hit = btb_valid[bi] && (btb_tag[bi] == lookup_tag);

    assign pred_taken = hit && (btb_jump[bi] || pht_sel[1]);
    assign pred_redirect = pred_taken && !stall;
    assign pred_target = hit ? btb_target[bi] : 32'd0;
    assign pred_idx = idx;

    always @(posedge clk) begin
        if (rst) begin
            ghr <= 8'd0;
            for (i = 0; i < 256; i = i + 1)
                pht[i] <= 2'b01;
            for (i = 0; i < 32; i = i + 1) begin
                btb_valid[i] <= 1'b0;
                btb_tag[i] <= 26'd0;
                btb_target[i] <= 32'd0;
                btb_jump[i] <= 1'b0;
            end
        end else if (upd_en) begin
            if (upd_cond) begin
                case (pht[upd_idx])
                    2'b00: pht[upd_idx] <= upd_taken ? 2'b01 : 2'b00;
                    2'b01: pht[upd_idx] <= upd_taken ? 2'b10 : 2'b00;
                    2'b10: pht[upd_idx] <= upd_taken ? 2'b11 : 2'b01;
                    2'b11: pht[upd_idx] <= upd_taken ? 2'b11 : 2'b10;
                    default: pht[upd_idx] <= 2'b01;
                endcase
                ghr <= {ghr[6:0], upd_taken};
            end
            if (upd_taken) begin
                btb_valid[upd_pc[5:1]] <= 1'b1;
                btb_tag[upd_pc[5:1]] <= upd_pc[31:6];
                btb_target[upd_pc[5:1]] <= upd_target;
                btb_jump[upd_pc[5:1]] <= upd_jump;
            end
        end
    end
endmodule
