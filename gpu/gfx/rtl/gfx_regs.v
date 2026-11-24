module gfx_regs (
    input wire clk,
    input wire rst,
    input wire clear,
    input wire valid,
    input wire advance,
    input wire gfx,
    input wire [2:0] gfx_op,
    input wire [3:0] tmask,
    input wire [127:0] a,
    input wire [127:0] b,
    output reg [8:0] sc_x0,
    output reg [8:0] sc_y0,
    output reg [8:0] sc_x1,
    output reg [8:0] sc_y1
);
    wire do_cfg;
    wire [1:0] lane;
    wire [31:0] reg_no;
    wire [31:0] reg_val;

    assign do_cfg = valid & advance & gfx & (gfx_op == 3'd0) & (tmask != 4'd0);
    assign lane = tmask[0] ? 2'd0 :
                  tmask[1] ? 2'd1 :
                  tmask[2] ? 2'd2 : 2'd3;
    assign reg_no = a[lane * 32 +: 32];
    assign reg_val = b[lane * 32 +: 32];

    always @(posedge clk) begin
        if (rst || clear) begin
            sc_x0 <= 9'd0;
            sc_y0 <= 9'd0;
            sc_x1 <= 9'd320;
            sc_y1 <= 9'd240;
        end else if (do_cfg) begin
            case (reg_no)
                32'd0: sc_x0 <= reg_val[8:0];
                32'd1: sc_y0 <= reg_val[8:0];
                32'd2: sc_x1 <= reg_val[8:0];
                32'd3: sc_y1 <= reg_val[8:0];
                default: begin
                end
            endcase
        end
    end
endmodule
