module rvc_fp (
    input  wire [31:0] inst,
    input  wire [31:0] word_in,
    output reg  [31:0] word_out
);

    // Precompute register fields
    wire [4:0] rp1  = 5'd8 + {2'd0, inst[9:7]};
    wire [4:0] rp2  = 5'd8 + {2'd0, inst[4:2]};
    wire [4:0] rd   = inst[11:7];
    wire [4:0] rs2  = inst[6:2];

    // Compressed instruction identification
    wire [1:0]  op16     = inst[1:0];
    wire [2:0]  funct3_16 = inst[15:13];
    wire [4:0]  cid      = {op16, funct3_16};

    // Offset uimm for each instruction (12 bits)
    reg [11:0] uimm;

    always @* begin
        // Default
        word_out = word_in;
        uimm = 12'd0;

        case (cid)
            // C.FLD
            5'b00_001: begin
                uimm = {4'd0, inst[6:5], inst[12:10], 3'd0};
                word_out = {uimm, rp1, 3'b011, rp2, 7'b0000111};
            end
            // C.FLW
            5'b00_011: begin
                uimm = {5'd0, inst[5], inst[12:10], inst[6], 2'd0};
                word_out = {uimm, rp1, 3'b010, rp2, 7'b0000111};
            end
            // C.FSD
            5'b00_101: begin
                uimm = {4'd0, inst[6:5], inst[12:10], 3'd0};
                word_out = {uimm[11:5], rp2, rp1, 3'b011, uimm[4:0], 7'b0100111};
            end
            // C.FSW
            5'b00_111: begin
                uimm = {5'd0, inst[5], inst[12:10], inst[6], 2'd0};
                word_out = {uimm[11:5], rp2, rp1, 3'b010, uimm[4:0], 7'b0100111};
            end
            // C.FLDSP
            5'b10_001: begin
                uimm = {3'd0, inst[4:2], inst[12], inst[6:5], 3'd0};
                word_out = {uimm, 5'd2, 3'b011, rd, 7'b0000111};
            end
            // C.FLWSP
            5'b10_011: begin
                uimm = {4'd0, inst[3:2], inst[12], inst[6:4], 2'd0};
                word_out = {uimm, 5'd2, 3'b010, rd, 7'b0000111};
            end
            // C.FSDSP
            5'b10_101: begin
                uimm = {3'd0, inst[9:7], inst[12:10], 3'd0};
                word_out = {uimm[11:5], rs2, 5'd2, 3'b011, uimm[4:0], 7'b0100111};
            end
            // C.FSWSP
            5'b10_111: begin
                uimm = {4'd0, inst[8:7], inst[12:9], 2'd0};
                word_out = {uimm[11:5], rs2, 5'd2, 3'b010, uimm[4:0], 7'b0100111};
            end
            default: begin
                word_out = word_in;
            end
        endcase
    end

endmodule
