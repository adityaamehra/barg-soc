module decode (
    input  wire [31:0] inst,
    output wire [4:0]  rs1,
    output wire [4:0]  rs2,
    output wire [4:0]  rd,
    output wire [2:0]  immsel,
    output wire [2:0]  unit,
    output wire [3:0]  alu_op,
    output wire        a_sel,
    output wire        b_sel,
    output wire [2:0]  wb_src,
    output wire        regwrite,
    output wire [1:0]  ctrl,
    output wire [2:0]  br_op,
    output wire        mem_store,
    output wire [2:0]  mem_size,
    output wire [1:0]  md_op,
    output wire [2:0]  simt_op,
    output wire [1:0]  simt_mode,
    output wire [1:0]  tensor_op,
    output wire [11:0] csr_addr,
    output wire        illegal,
    output wire        gfx,
    output wire [2:0]  gfx_op
);

    wire [6:0] op  = inst[6:0];
    wire [2:0] f3  = inst[14:12];
    wire [6:0] f7  = inst[31:25];

    assign rs1       = inst[19:15];
    assign rs2       = inst[24:20];
    assign rd        = inst[11:7];
    assign br_op     = f3;
    assign mem_size  = f3;
    assign md_op     = f3[1:0];
    assign simt_op   = f3;
    assign simt_mode = inst[26:25];
    assign tensor_op = f3[1:0];
    assign csr_addr  = inst[31:20];
    assign gfx_op    = f3;

    reg        r_immsel;
    reg [2:0]  r_immsel3;
    reg [2:0]  r_unit;
    reg [3:0]  r_alu_op;
    reg        r_a_sel;
    reg        r_b_sel;
    reg [2:0]  r_wb_src;
    reg        r_regwrite;
    reg [1:0]  r_ctrl;
    reg        r_mem_store;
    reg        r_illegal;
    reg        r_gfx;

    always @* begin
        r_immsel3   = 3'd5;
        r_unit      = 3'd7;
        r_alu_op    = 4'd0;
        r_a_sel     = 1'b0;
        r_b_sel     = 1'b0;
        r_wb_src    = 3'd0;
        r_regwrite  = 1'b0;
        r_ctrl      = 2'd0;
        r_mem_store = 1'b0;
        r_illegal   = 1'b0;
        r_gfx       = 1'b0;

        case (op)
            7'h37: begin // LUI
                r_unit     = 3'd0;
                r_alu_op   = 4'd10;
                r_b_sel    = 1'b1;
                r_immsel3  = 3'd3;
                r_regwrite = 1'b1;
            end
            7'h17: begin // AUIPC
                r_unit     = 3'd0;
                r_alu_op   = 4'd0;
                r_a_sel    = 1'b1;
                r_b_sel    = 1'b1;
                r_immsel3  = 3'd3;
                r_regwrite = 1'b1;
            end
            7'h6F: begin // JAL
                r_unit     = 3'd0;
                r_a_sel    = 1'b1;
                r_b_sel    = 1'b1;
                r_immsel3  = 3'd4;
                r_wb_src   = 3'd7;
                r_regwrite = 1'b1;
                r_ctrl     = 2'd2;
            end
            7'h67: begin // JALR
                if (f3 == 3'd0) begin
                    r_unit     = 3'd0;
                    r_b_sel    = 1'b1;
                    r_immsel3  = 3'd0;
                    r_wb_src   = 3'd7;
                    r_regwrite = 1'b1;
                    r_ctrl     = 2'd3;
                end else begin
                    r_illegal = 1'b1;
                end
            end
            7'h63: begin // Branch
                if (f3 != 3'd2 && f3 != 3'd3) begin
                    r_unit    = 3'd0;
                    r_immsel3 = 3'd2;
                    r_ctrl    = 2'd1;
                end else begin
                    r_illegal = 1'b1;
                end
            end
            7'h03: begin // Load
                if (f3 == 3'd0 || f3 == 3'd1 || f3 == 3'd2 || f3 == 3'd4 || f3 == 3'd5) begin
                    r_unit     = 3'd3;
                    r_b_sel    = 1'b1;
                    r_immsel3  = 3'd0;
                    r_wb_src   = 3'd3;
                    r_regwrite = 1'b1;
                end else begin
                    r_illegal = 1'b1;
                end
            end
            7'h23: begin // Store
                if (f3 == 3'd0 || f3 == 3'd1 || f3 == 3'd2) begin
                    r_unit      = 3'd3;
                    r_b_sel     = 1'b1;
                    r_immsel3   = 3'd1;
                    r_mem_store = 1'b1;
                end else begin
                    r_illegal = 1'b1;
                end
            end
            7'h13: begin // OP-IMM
                case (f3)
                    3'd0: begin r_unit = 3'd0; r_b_sel = 1'b1; r_immsel3 = 3'd0; r_regwrite = 1'b1; r_alu_op = 4'd0; end
                    3'd2: begin r_unit = 3'd0; r_b_sel = 1'b1; r_immsel3 = 3'd0; r_regwrite = 1'b1; r_alu_op = 4'd3; end
                    3'd3: begin r_unit = 3'd0; r_b_sel = 1'b1; r_immsel3 = 3'd0; r_regwrite = 1'b1; r_alu_op = 4'd4; end
                    3'd4: begin r_unit = 3'd0; r_b_sel = 1'b1; r_immsel3 = 3'd0; r_regwrite = 1'b1; r_alu_op = 4'd5; end
                    3'd6: begin r_unit = 3'd0; r_b_sel = 1'b1; r_immsel3 = 3'd0; r_regwrite = 1'b1; r_alu_op = 4'd8; end
                    3'd7: begin r_unit = 3'd0; r_b_sel = 1'b1; r_immsel3 = 3'd0; r_regwrite = 1'b1; r_alu_op = 4'd9; end
                    3'd1: begin
                        if (f7 == 7'd0) begin
                            r_unit = 3'd0; r_b_sel = 1'b1; r_immsel3 = 3'd0; r_regwrite = 1'b1; r_alu_op = 4'd2;
                        end else begin
                            r_illegal = 1'b1;
                        end
                    end
                    3'd5: begin
                        if (f7 == 7'd0) begin
                            r_unit = 3'd0; r_b_sel = 1'b1; r_immsel3 = 3'd0; r_regwrite = 1'b1; r_alu_op = 4'd6;
                        end else if (f7 == 7'h20) begin
                            r_unit = 3'd0; r_b_sel = 1'b1; r_immsel3 = 3'd0; r_regwrite = 1'b1; r_alu_op = 4'd7;
                        end else begin
                            r_illegal = 1'b1;
                        end
                    end
                    default: r_illegal = 1'b1;
                endcase
            end
            7'h33: begin // OP
                if (f7 == 7'd0) begin
                    r_unit     = 3'd0;
                    r_regwrite = 1'b1;
                    case (f3)
                        3'd0: r_alu_op = 4'd0;
                        3'd1: r_alu_op = 4'd2;
                        3'd2: r_alu_op = 4'd3;
                        3'd3: r_alu_op = 4'd4;
                        3'd4: r_alu_op = 4'd5;
                        3'd5: r_alu_op = 4'd6;
                        3'd6: r_alu_op = 4'd8;
                        3'd7: r_alu_op = 4'd9;
                    endcase
                end else if (f7 == 7'h20) begin
                    if (f3 == 3'd0) begin
                        r_unit = 3'd0; r_regwrite = 1'b1; r_alu_op = 4'd1;
                    end else if (f3 == 3'd5) begin
                        r_unit = 3'd0; r_regwrite = 1'b1; r_alu_op = 4'd7;
                    end else begin
                        r_illegal = 1'b1;
                    end
                end else if (f7 == 7'd1) begin
                    r_regwrite = 1'b1;
                    if (f3 < 3'd4) begin
                        r_unit  = 3'd1;
                        r_wb_src = 3'd1;
                    end else begin
                        r_unit  = 3'd2;
                        r_wb_src = 3'd2;
                    end
                end else begin
                    r_illegal = 1'b1;
                end
            end
            7'h0F: begin // FENCE
            end
            7'h73: begin // SYSTEM
                if ((f3 == 3'd2 || f3 == 3'd3 || f3 == 3'd6 || f3 == 3'd7) && inst[19:15] == 5'd0) begin
                    r_unit     = 3'd6;
                    r_wb_src   = 3'd6;
                    r_regwrite = 1'b1;
                end else begin
                    r_illegal = 1'b1;
                end
            end
            7'h0B: begin // SIMT
                if ((f3 <= 3'd4 && f7 == 7'd0) ||
                    (f3 == 3'd5 && f7 <= 7'd2) ||
                    (f3 == 3'd6 && f7 <= 7'd3)) begin
                    r_unit   = 3'd4;
                    r_wb_src = 3'd4;
                    if (f3 == 3'd5 || f3 == 3'd6)
                        r_regwrite = 1'b1;
                end else begin
                    r_illegal = 1'b1;
                end
            end
            7'h2B: begin // Tensor
                if (f7 == 7'd0 && f3 <= 3'd3) begin
                    if ((f3 == 3'd0 && inst[11:7] == 5'd0) ||
                        (f3 == 3'd1) ||
                        (f3 == 3'd2 && inst[11:7] == 5'd0) ||
                        (f3 == 3'd3 && inst[11:7] == 5'd0 && inst[19:15] == 5'd0 && inst[24:20] == 5'd0)) begin
                        r_unit   = 3'd5;
                        r_wb_src = 3'd5;
                        if (f3 == 3'd1)
                            r_regwrite = 1'b1;
                    end else begin
                        r_illegal = 1'b1;
                    end
                end else begin
                    r_illegal = 1'b1;
                end
            end
            7'h5B: begin // Graphics
                if (f7 == 7'd0 && (f3 == 3'd0 || f3 == 3'd5)) begin
                    if (inst[11:7] == 5'd0) begin
                        r_gfx = 1'b1;
                    end else begin
                        r_illegal = 1'b1;
                    end
                end else if (f7 == 7'd0 && (f3 == 3'd1 || f3 == 3'd3 || f3 == 3'd4 || f3 == 3'd6)) begin
                    r_gfx      = 1'b1;
                    r_regwrite = 1'b1;
                end else begin
                    r_illegal = 1'b1;
                end
            end
            default: begin
                r_illegal = 1'b1;
            end
        endcase
    end

    assign immsel    = r_immsel3;
    assign unit      = r_unit;
    assign alu_op    = r_alu_op;
    assign a_sel     = r_a_sel;
    assign b_sel     = r_b_sel;
    assign wb_src    = r_wb_src;
    assign regwrite  = r_regwrite;
    assign ctrl      = r_ctrl;
    assign mem_store = r_mem_store;
    assign illegal   = r_illegal;
    assign gfx       = r_gfx;

endmodule
