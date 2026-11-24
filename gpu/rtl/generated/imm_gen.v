module imm_gen (
    input  [31:0] inst,
    input  [2:0]  immsel,
    output reg [31:0] imm
);

    always @* begin
        case (immsel)
            3'b000: imm = {{20{inst[31]}}, inst[31:20]};
            3'b001: imm = {{20{inst[31]}}, inst[31:25], inst[11:7]};
            3'b010: imm = {{19{inst[31]}}, inst[31], inst[7], inst[30:25], inst[11:8], 1'b0};
            3'b011: imm = {inst[31:12], 12'd0};
            3'b100: imm = {{11{inst[31]}}, inst[31], inst[19:12], inst[20], inst[30:21], 1'b0};
            3'b101: imm = 32'd0;
            3'b110: imm = 32'd0;
            3'b111: imm = 32'd0;
            default: imm = 32'd0;
        endcase
    end

endmodule
