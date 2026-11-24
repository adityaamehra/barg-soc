module ifault_pmp(
    input  [31:0] inst,
    input         is16,
    input  [31:0] pc,
    input  [31:0] word_lo,
    input         xlate,
    input         lo_pf,
    input         lo_af,
    input         hi_pf,
    input         hi_af,
    input         pmp_lo,
    input         pmp_hi,
    output reg [31:0] inst_out,
    output reg        is16_out
);

    // Determine if the next word is needed
    wire need_hi = pc[1] & (word_lo[17:16] == 2'b11);

    // Fault word constants
wire [31:0] fault_page_pc   = 32'b0 | 32'b0001011 | (32'b001 << 12) | (32'b0 << 20);
wire [31:0] fault_access_pc = 32'b0 | 32'b0001011 | (32'b010 << 12) | (32'b0 << 20);
wire [31:0] fault_page_hi   = 32'b0 | 32'b0001011 | (32'b001 << 12) | (32'b1 << 20);
wire [31:0] fault_access_hi = 32'b0 | 32'b0001011 | (32'b010 << 12) | (32'b1 << 20);

    // Combinational logic
    always @* begin
        // Default: pass through
        inst_out = inst;
        is16_out = is16;

        // Priority order
        if (xlate && lo_pf) begin
            inst_out = fault_page_pc;
            is16_out = 1'b0;
        end else if ((xlate && lo_af) || pmp_lo) begin
            inst_out = fault_access_pc;
            is16_out = 1'b0;
        end else if (xlate && need_hi && hi_pf) begin
            inst_out = fault_page_hi;
            is16_out = 1'b0;
        end else if (need_hi && ((xlate && hi_af) || pmp_hi)) begin
            inst_out = fault_access_hi;
            is16_out = 1'b0;
        end
    end

endmodule
