module fp_dec (
    input  wire [31:0] inst,
    input  wire [1:0]  fs,
    input  wire [2:0]  frm,
    output wire        is_fp,
    output wire        is_dw,
    output wire [31:0] dec_inst
);

    wire [6:0]  opcode = inst[6:0];
    wire [2:0]  f3     = inst[14:12];
    wire [1:0]  fmt    = inst[26:25];
    wire [4:0]  f5     = inst[31:27];
    wire [4:0]  rs2f   = inst[24:20];

    wire rm_ok = (f3 == 3'd0) || (f3 == 3'd1) || (f3 == 3'd2) || (f3 == 3'd3) || (f3 == 3'd4) ||
                 ((f3 == 3'd7) && ((frm == 3'd0) || (frm == 3'd1) || (frm == 3'd2) || (frm == 3'd3) || (frm == 3'd4)));

    wire is_load  = (opcode == 7'b0000111) && ((f3 == 3'b010) || (f3 == 3'b011));
    wire is_store = (opcode == 7'b0100111) && ((f3 == 3'b010) || (f3 == 3'b011));

    wire is_fused = ((opcode == 7'b1000011) || (opcode == 7'b1000111) ||
                     (opcode == 7'b1001011) || (opcode == 7'b1001111)) &&
                    ((fmt == 2'b00) || (fmt == 2'b01)) && rm_ok;

    wire is_arith = (opcode == 7'b1010011) && ((fmt == 2'b00) || (fmt == 2'b01)) && (
        ((f5 == 5'b00000) || (f5 == 5'b00001) || (f5 == 5'b00010) || (f5 == 5'b00011)) && rm_ok ||
        (f5 == 5'b01011) && (rs2f == 5'b00000) && rm_ok ||
        (f5 == 5'b00100) && ((f3 == 3'b000) || (f3 == 3'b001) || (f3 == 3'b010)) ||
        (f5 == 5'b00101) && ((f3 == 3'b000) || (f3 == 3'b001)) ||
        (f5 == 5'b01000) && rm_ok && (((fmt == 2'b00) && (rs2f == 5'b00001)) || ((fmt == 2'b01) && (rs2f == 5'b00000))) ||
        (f5 == 5'b10100) && ((f3 == 3'b000) || (f3 == 3'b001) || (f3 == 3'b010)) ||
        (f5 == 5'b11000) && ((rs2f == 5'b00000) || (rs2f == 5'b00001)) && rm_ok ||
        (f5 == 5'b11010) && ((rs2f == 5'b00000) || (rs2f == 5'b00001)) && rm_ok ||
        (f5 == 5'b11100) && (rs2f == 5'b00000) && ((f3 == 3'b001) || ((f3 == 3'b000) && (fmt == 2'b00))) ||
        (f5 == 5'b11110) && (rs2f == 5'b00000) && (f3 == 3'b000) && (fmt == 2'b00)
    );

    wire is_fp_inst = is_load || is_store || is_fused || is_arith;

    assign is_fp = is_fp_inst && (fs != 2'b00);
    assign is_dw = is_fp && ((opcode == 7'b0000111) || (opcode == 7'b0100111)) && (f3 == 3'b011);

    wire [31:0] dec_inst_load  = {inst[31:15], 3'b010, 5'b00000, 7'b0000011};
    wire [31:0] dec_inst_store = {inst[31:15], 3'b010, inst[11:7], 7'b0100011};
    wire [31:0] dec_inst_fused = {7'b0000000, inst[24:20], inst[19:15], 3'b000, 5'b00000, 7'b0110011};
    wire [31:0] dec_inst_arith_common = {7'b0000000, inst[24:20], inst[19:15], 3'b000, 5'b00000, 7'b0110011};
    wire [31:0] dec_inst_arith_rd     = {7'b0000000, inst[24:20], inst[19:15], 3'b000, inst[11:7], 7'b0110011};

    wire use_arith_rd = (f5 == 5'b10100) || (f5 == 5'b11000) || (f5 == 5'b11100);

    assign dec_inst = is_fp ? (
                          is_load  ? dec_inst_load :
                          is_store ? dec_inst_store :
                          is_fused ? dec_inst_fused :
                          (is_arith ? (use_arith_rd ? dec_inst_arith_rd : dec_inst_arith_common) : 32'b0)
                      ) : inst;

endmodule
