module ifault (
    input  wire [31:0] inst,
    input  wire        is16,
    input  wire [31:0] pc,
    input  wire [31:0] word_lo,
    input  wire        xlate,
    input  wire        lo_pf,
    input  wire        lo_af,
    input  wire        hi_pf,
    input  wire        hi_af,
    output reg  [31:0] inst_out,
    output reg         is16_out
);

    wire need_hi = pc[1] & (word_lo[17:16] == 2'b11);

    always @* begin
        if (xlate && (lo_pf || lo_af)) begin
            inst_out = 32'h0000000B;
            inst_out[14:12] = lo_pf ? 3'b001 : 3'b010;
            is16_out = 1'b0;
        end else if (xlate && need_hi && (hi_pf || hi_af)) begin
            inst_out = 32'h0010000B;
            inst_out[14:12] = hi_pf ? 3'b001 : 3'b010;
            is16_out = 1'b0;
        end else begin
            inst_out = inst;
            is16_out = is16;
        end
    end

endmodule
