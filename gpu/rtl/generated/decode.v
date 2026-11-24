module decode (
    input [31:0] inst,
    output reg [4:0] rs1,
    output reg [4:0] rs2,
    output reg [4:0] rd,
    output reg [2:0] immsel,
    output reg [2:0] unit,
    output reg [3:0] alu_op,
    output reg a_sel,
    output reg b_sel,
    output reg [2:0] wb_src,
    output reg regwrite,
    output reg [1:0] ctrl,
    output reg [2:0] br_op,
    output reg mem_store,
    output reg [2:0] mem_size,
    output reg [1:0] md_op,
    output reg [2:0] simt_op,
    output reg [1:0] simt_mode,
    output reg [1:0] tensor_op,
    output reg [11:0] csr_addr,
    output reg illegal
);

wire [6:0] op;
wire [2:0] f3;
wire [6:0] f7;

assign op = inst[6:0];
assign f3 = inst[14:12];
assign f7 = inst[31:25];

always @* begin
    rs1 = inst[19:15];
    rs2 = inst[24:20];
    rd = inst[11:7];
    csr_addr = inst[31:20];
    br_op = f3;
    mem_size = f3;
    simt_op = f3;
    md_op = f3[1:0];
    tensor_op = f3[1:0];
    simt_mode = f7[1:0];

    immsel = 3'b101;
    unit = 3'b111;
    alu_op = 4'b0000;
    a_sel = 1'b0;
    b_sel = 1'b0;
    wb_src = 3'b000;
    regwrite = 1'b0;
    ctrl = 2'b00;
    mem_store = 1'b0;
    illegal = 1'b0;

    case (op)
        7'h37: begin
            unit = 3'b000;
            alu_op = 4'b1010;
            b_sel = 1'b1;
            immsel = 3'b011;
            regwrite = 1'b1;
        end

        7'h17: begin
            unit = 3'b000;
            alu_op = 4'b0000;
            a_sel = 1'b1;
            b_sel = 1'b1;
            immsel = 3'b011;
            regwrite = 1'b1;
        end

        7'h6F: begin
            unit = 3'b000;
            a_sel = 1'b1;
            b_sel = 1'b1;
            immsel = 3'b100;
            wb_src = 3'b111;
            regwrite = 1'b1;
            ctrl = 2'b10;
        end

        7'h67: begin
            if (f3 == 3'd0) begin
                unit = 3'b000;
                b_sel = 1'b1;
                immsel = 3'b000;
                wb_src = 3'b111;
                regwrite = 1'b1;
                ctrl = 2'b11;
            end else begin
                illegal = 1'b1;
            end
        end

        7'h63: begin
            if ((f3 != 3'd2) && (f3 != 3'd3)) begin
                unit = 3'b000;
                immsel = 3'b010;
                ctrl = 2'b01;
            end else begin
                illegal = 1'b1;
            end
        end

        7'h03: begin
            if ((f3 == 3'd0) || (f3 == 3'd1) || (f3 == 3'd2) ||
                (f3 == 3'd4) || (f3 == 3'd5)) begin
                unit = 3'b011;
                b_sel = 1'b1;
                immsel = 3'b000;
                wb_src = 3'b011;
                regwrite = 1'b1;
            end else begin
                illegal = 1'b1;
            end
        end

        7'h23: begin
            if ((f3 == 3'd0) || (f3 == 3'd1) || (f3 == 3'd2)) begin
                unit = 3'b011;
                b_sel = 1'b1;
                immsel = 3'b001;
                mem_store = 1'b1;
            end else begin
                illegal = 1'b1;
            end
        end

        7'h13: begin
            b_sel = 1'b1;
            immsel = 3'b000;
            regwrite = 1'b1;
            unit = 3'b000;

            case (f3)
                3'd0: alu_op = 4'b0000;
                3'd1: begin
                    if (f7 == 7'd0) begin
                        alu_op = 4'b0010;
                    end else begin
                        illegal = 1'b1;
                    end
                end
                3'd2: alu_op = 4'b0011;
                3'd3: alu_op = 4'b0100;
                3'd4: alu_op = 4'b0101;
                3'd5: begin
                    if (f7 == 7'd0) begin
                        alu_op = 4'b0110;
                    end else if (f7 == 7'h20) begin
                        alu_op = 4'b0111;
                    end else begin
                        illegal = 1'b1;
                    end
                end
                3'd6: alu_op = 4'b1000;
                3'd7: alu_op = 4'b1001;
                default: illegal = 1'b1;
            endcase
        end

        7'h33: begin
            regwrite = 1'b1;

            case (f7)
                7'h00: begin
                    unit = 3'b000;
                    case (f3)
                        3'd0: alu_op = 4'b0000;
                        3'd1: alu_op = 4'b0010;
                        3'd2: alu_op = 4'b0011;
                        3'd3: alu_op = 4'b0100;
                        3'd4: alu_op = 4'b0101;
                        3'd5: alu_op = 4'b0110;
                        3'd6: alu_op = 4'b1000;
                        3'd7: alu_op = 4'b1001;
                        default: illegal = 1'b1;
                    endcase
                end

                7'h20: begin
                    unit = 3'b000;
                    if (f3 == 3'd0) begin
                        alu_op = 4'b0001;
                    end else if (f3 == 3'd5) begin
                        alu_op = 4'b0111;
                    end else begin
                        illegal = 1'b1;
                    end
                end

                7'h01: begin
                    if (f3 < 3'd4) begin
                        unit = 3'b001;
                        wb_src = 3'b001;
                    end else begin
                        unit = 3'b010;
                        wb_src = 3'b010;
                    end
                end

                default: illegal = 1'b1;
            endcase
        end

        7'h0F: begin
        end

        7'h73: begin
            if (((f3 == 3'd2) || (f3 == 3'd3) || (f3 == 3'd6) || (f3 == 3'd7)) &&
                (inst[19:15] == 5'd0)) begin
                unit = 3'b110;
                wb_src = 3'b110;
                regwrite = 1'b1;
            end else begin
                illegal = 1'b1;
            end
        end

        7'h0B: begin
            if (((f7 == 7'd0) && (f3 <= 3'd4)) ||
                ((f3 == 3'd5) && (f7 <= 7'd2)) ||
                ((f3 == 3'd6) && (f7 <= 7'd3))) begin
                unit = 3'b100;
                wb_src = 3'b100;
                if ((f3 == 3'd5) || (f3 == 3'd6)) begin
                    regwrite = 1'b1;
                end
            end else begin
                illegal = 1'b1;
            end
        end

        7'h2B: begin
            if ((f7 == 7'd0) && (f3 <= 3'd3) &&
                (((f3 == 3'd0) && (inst[11:7] == 5'd0)) ||
                 (f3 == 3'd1) ||
                 ((f3 == 3'd2) && (inst[11:7] == 5'd0)) ||
                 ((f3 == 3'd3) && (inst[11:7] == 5'd0) &&
                  (inst[19:15] == 5'd0) && (inst[24:20] == 5'd0)))) begin
                unit = 3'b101;
                wb_src = 3'b101;
                if (f3 == 3'd1) begin
                    regwrite = 1'b1;
                end
            end else begin
                illegal = 1'b1;
            end
        end

        default: illegal = 1'b1;
    endcase

    if (illegal) begin
        immsel = 3'b101;
        unit = 3'b111;
        alu_op = 4'b0000;
        a_sel = 1'b0;
        b_sel = 1'b0;
        wb_src = 3'b000;
        regwrite = 1'b0;
        ctrl = 2'b00;
        mem_store = 1'b0;
    end
end

endmodule
