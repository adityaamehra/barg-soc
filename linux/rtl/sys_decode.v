module sys_decode (
    input  wire [31:0] inst,
    input  wire [1:0]  priv,
    output reg         xcpt,
    output reg [3:0]   cause,
    output reg [2:0]   csrop,
    output reg         csr_imm,
    output reg         is_csr,
    output reg         is_mret,
    output reg         is_amo,
    output reg [3:0]   amo_op
);

    wire [6:0] opcode  = inst[6:0];
    wire [2:0] funct3  = inst[14:12];
    wire [6:0] funct7  = inst[31:25];
    wire [4:0] rs1     = inst[19:15];
    wire [4:0] rs2     = inst[24:20];

    reg illegal_flag;

    always @* begin
        // Defaults
        xcpt     = 1'b0;
        cause    = 4'b0;
        csrop    = 3'b0;
        csr_imm  = 1'b0;
        is_csr   = 1'b0;
        is_mret  = 1'b0;
        is_amo   = 1'b0;
        amo_op   = 4'b0;
        illegal_flag = 1'b0;

        // Independent: is_mret
        if (inst == 32'h30200073)
            is_mret = 1'b1;

        // Independent: is_amo and amo_op
        if (opcode == 7'b0101111 && funct3 == 3'b010) begin
            case (inst[31:27])
                5'b00010: if (inst[24:20] == 5'b00000) begin is_amo = 1'b1; amo_op = 4'b0001; end // AMO_LR
                5'b00011: begin is_amo = 1'b1; amo_op = 4'b0010; end // AMO_SC
                5'b00001: begin is_amo = 1'b1; amo_op = 4'b0011; end // AMO_SWAP
                5'b00000: begin is_amo = 1'b1; amo_op = 4'b0100; end // AMO_ADD
                5'b00100: begin is_amo = 1'b1; amo_op = 4'b0101; end // AMO_XOR
                5'b01100: begin is_amo = 1'b1; amo_op = 4'b0110; end // AMO_AND
                5'b01000: begin is_amo = 1'b1; amo_op = 4'b0111; end // AMO_OR
                5'b10000: begin is_amo = 1'b1; amo_op = 4'b1000; end // AMO_MIN
                5'b10100: begin is_amo = 1'b1; amo_op = 4'b1001; end // AMO_MAX
                5'b11000: begin is_amo = 1'b1; amo_op = 4'b1010; end // AMO_MINU
                5'b11100: begin is_amo = 1'b1; amo_op = 4'b1011; end // AMO_MAXU
                default: begin is_amo = 1'b0; amo_op = 4'b0; end
            endcase
        end

        // Priority decoding for exception/CSR outputs
        // 1. Fetch-fault word
        if (opcode == 7'b0001011 && (funct3 == 3'b001 || funct3 == 3'b010)) begin
            xcpt  = 1'b1;
            cause = (funct3 == 3'b001) ? 4'd12 : 4'd1;
        end
        // 2. ebreak
        else if (inst == 32'h00100073) begin
            xcpt  = 1'b1;
            cause = 4'd3;
        end
        // 3. ecall
        else if (inst == 32'h00000073) begin
            xcpt = 1'b1;
            case (priv)
                2'b00: cause = 4'd8;
                2'b01: cause = 4'd9;
                2'b10, 2'b11: cause = 4'd11;
                default: cause = 4'd11;
            endcase
        end
        // 4. sret
        else if (inst == 32'h10200073) begin
            csrop = 3'b101;
        end
        // 5. sfence.vma
        else if (opcode == 7'b1110011 && funct3 == 3'b000 && funct7 == 7'b0001001 && inst[11:7] == 5'b00000) begin
            csrop = 3'b110;
        end
        // 6. fence.i
        else if (opcode == 7'b0001111 && funct3 == 3'b001) begin
            csrop = 3'b111;
        end
        // 7. CSR instructions
        else if (opcode == 7'b1110011 && (funct3 == 3'b001 || funct3 == 3'b010 || funct3 == 3'b011 ||
                                           funct3 == 3'b101 || funct3 == 3'b110 || funct3 == 3'b111)) begin
            is_csr  = 1'b1;
            csr_imm = funct3[2];
            case (funct3[1:0])
                2'b01: csrop = 3'b010;                       // CSR_WRITE
                2'b10: csrop = (rs1 != 5'b0) ? 3'b011 : 3'b001; // CSR_SET / CSR_READ
                2'b11: csrop = (rs1 != 5'b0) ? 3'b100 : 3'b001; // CSR_CLEAR / CSR_READ
                default: csrop = 3'b000;
            endcase
        end
        // 8. All other legal instructions (produce zeros) or illegal
        else begin
            case (opcode)
                7'b0110111: ; // LUI
                7'b0010111: ; // AUIPC
                7'b1101111: ; // JAL
                7'b1100111: if (funct3 != 3'b000) illegal_flag = 1'b1; // JALR
                7'b1100011: if (!(funct3 == 3'b000 || funct3 == 3'b001 || funct3 == 3'b100 ||
                                   funct3 == 3'b101 || funct3 == 3'b110 || funct3 == 3'b111)) illegal_flag = 1'b1; // Branch
                7'b0000011: if (!(funct3 == 3'b000 || funct3 == 3'b001 || funct3 == 3'b010 ||
                                   funct3 == 3'b100 || funct3 == 3'b101)) illegal_flag = 1'b1; // Load
                7'b0100011: if (!(funct3 == 3'b000 || funct3 == 3'b001 || funct3 == 3'b010)) illegal_flag = 1'b1; // Store
                7'b0010011: begin // Imm arithmetic
                    if (funct3 == 3'b000 || funct3 == 3'b010 || funct3 == 3'b011 ||
                        funct3 == 3'b100 || funct3 == 3'b110 || funct3 == 3'b111) ;
                    else if (funct3 == 3'b001 && funct7 == 7'b0000000) ;
                    else if (funct3 == 3'b101 && (funct7 == 7'b0000000 || funct7 == 7'b0100000)) ;
                    else illegal_flag = 1'b1;
                end
                7'b0110011: begin // Register arithmetic
                    if (funct7 == 7'b0000000) ;
                    else if (funct7 == 7'b0100000 && (funct3 == 3'b000 || funct3 == 3'b101)) ;
                    else if (funct7 == 7'b0000001) ;
                    else illegal_flag = 1'b1;
                end
                7'b0001111: if (funct3 != 3'b000) illegal_flag = 1'b1; // Fence (funct3=000)
                7'b0101111: if (!(funct3 == 3'b010 && is_amo)) illegal_flag = 1'b1; // Atomic (only legal if is_amo)
                7'b1110011: begin // System
                    if (funct3 == 3'b000) begin
                        // Only mret and wfi are legal here (others handled above)
                        if (!(inst == 32'h30200073 || inst == 32'h10500073)) illegal_flag = 1'b1;
                    end
                    else begin
                        // CSR funct3 handled above
                        illegal_flag = 1'b1;
                    end
                end
                default: illegal_flag = 1'b1;
            endcase

            if (illegal_flag) begin
                xcpt  = 1'b1;
                cause = 4'd2; // ILLEGAL_INSTRUCTION
            end
        end
    end

endmodule
