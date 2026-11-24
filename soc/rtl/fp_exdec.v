module fp_exdec (
    input  wire [31:0] inst,
    input  wire        valid,
    input  wire        xcpt,
    input  wire [2:0]  frm,
    output wire        is_fpu,
    output wire        is_fst,
    output wire        int_dest,
    output wire [4:0]  op,
    output wire        dbl,
    output wire [2:0]  rm,
    output wire [4:0]  ra1,
    output wire [4:0]  ra2,
    output wire [4:0]  ra3
);

    wire active = valid & ~xcpt;

    wire [6:0] opcode = inst[6:0];
    wire [2:0] f3     = inst[14:12];
    wire [1:0] fmt    = inst[26:25];
    wire [4:0] f5     = inst[31:27];
    wire [4:0] rs2f   = inst[24:20];

    assign ra1 = inst[19:15];
    assign ra2 = inst[24:20];
    assign ra3 = inst[31:27];

    wire is_fpu_opcode = (opcode == 7'b1000011) | (opcode == 7'b1000111) |
                         (opcode == 7'b1001011) | (opcode == 7'b1001111) |
                         (opcode == 7'b1010011);
    assign is_fpu = active & is_fpu_opcode;
    assign is_fst = active & (opcode == 7'b0100111);

    assign int_dest = is_fpu & (opcode == 7'b1010011) &
                      ( (f5 == 5'b10100) | (f5 == 5'b11000) | (f5 == 5'b11100) );

    reg [4:0] op_reg;
    always @* begin
        op_reg = 5'd0;
        case (opcode)
            7'b1000011: op_reg = 5'd5;
            7'b1000111: op_reg = 5'd6;
            7'b1001011: op_reg = 5'd7;
            7'b1001111: op_reg = 5'd8;
            7'b1010011: begin
                case (f5)
                    5'b00000: op_reg = 5'd0;
                    5'b00001: op_reg = 5'd1;
                    5'b00010: op_reg = 5'd2;
                    5'b00011: op_reg = 5'd3;
                    5'b01011: op_reg = 5'd4;
                    5'b00100: op_reg = 5'd9 + {2'b00, f3};
                    5'b00101: op_reg = 5'd12 + {2'b00, f3};
                    5'b01000: op_reg = (fmt == 2'b00) ? 5'd22 : 5'd23;
                    5'b10100: begin
                        case (f3)
                            3'b010: op_reg = 5'd14;
                            3'b001: op_reg = 5'd15;
                            default: op_reg = 5'd16;
                        endcase
                    end
                    5'b11000: op_reg = 5'd18 + rs2f[0];
                    5'b11010: op_reg = 5'd20 + rs2f[0];
                    5'b11100: op_reg = (f3 == 3'b001) ? 5'd17 : 5'd24;
                    5'b11110: op_reg = 5'd25;
                    default: op_reg = 5'd0;
                endcase
            end
            default: op_reg = 5'd0;
        endcase
    end
    assign op = op_reg;

    assign dbl = (opcode == 7'b1010011 && f5 == 5'b01000) ? 1'b0 : fmt[0];

    reg [2:0] rm_reg;
    always @* begin
        rm_reg = 3'b000;
        if ( (opcode == 7'b1000011) | (opcode == 7'b1000111) |
             (opcode == 7'b1001011) | (opcode == 7'b1001111) |
             ( (opcode == 7'b1010011) &
               ( (f5 == 5'b00000) | (f5 == 5'b00001) | (f5 == 5'b00010) | (f5 == 5'b00011) |
                 (f5 == 5'b01011) | (f5 == 5'b01000) | (f5 == 5'b11000) | (f5 == 5'b11010) ) ) ) begin
            rm_reg = (f3 == 3'b111) ? frm : f3;
        end
    end
    assign rm = rm_reg;

endmodule
