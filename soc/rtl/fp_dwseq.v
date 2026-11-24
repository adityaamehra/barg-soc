module fp_dwseq (
    input  wire        clk,
    input  wire        rst,
    input  wire        is_dw,
    input  wire        valid,
    input  wire        xcpt,
    input  wire        stall,
    input  wire        flush,
    input  wire [31:0] imm_in,
    output wire        half2,
    output wire        hold,
    output wire [1:0]  dwsel,
    output wire [31:0] imm_out
);

    wire dw = is_dw & valid & ~xcpt;
    wire accept = ~stall & ~flush;

    assign hold = dw & ~half2;

    assign dwsel = (dw == 1'b0) ? 2'b00 :
                   (half2 == 1'b0) ? 2'b01 : 2'b10;

    assign imm_out = (dw & half2) ? (imm_in + 32'd4) : imm_in;

    reg half2_reg;
    assign half2 = half2_reg;

    always @(posedge clk) begin
        if (rst) begin
            half2_reg <= 1'b0;
        end else begin
            if (flush) begin
                half2_reg <= 1'b0;
            end else if (dw & accept) begin
                half2_reg <= ~half2_reg;
            end else if (~dw) begin
                half2_reg <= 1'b0;
            end
        end
    end

endmodule
