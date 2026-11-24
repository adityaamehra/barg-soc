module ex_xcpt
(
    input  wire          id_xcpt,
    input  wire [3:0]    id_cause,
    input  wire          id_irq,
    input  wire [31:0]   inst,
    input  wire [31:0]   pc,
    input  wire [2:0]    memtype,
    input  wire          memwrite,
    input  wire [31:0]   alu_y,
    input  wire          d_pf,
    input  wire          d_af,
    input  wire          d_store,
    output wire          xcpt,
    output wire [3:0]    cause,
    output wire [31:0]   tval,
    output wire          memwrite_out
);

    // Misaligned access detection
    wire misaligned;
    assign misaligned =
        (((memtype == 3'b010) || (memtype == 3'b110) || (memtype == 3'b111)) &&
         (alu_y[1:0] != 2'b00)) ||
        (((memtype == 3'b001) || (memtype == 3'b100)) &&
         (alu_y[0] == 1'b1));

    // Priority logic
    reg          xcpt_reg;
    reg  [3:0]   cause_reg;
    reg  [31:0]  tval_reg;
    reg          memwrite_out_reg;

    always @*
    begin
        // Default values
        xcpt_reg          = 1'b0;
        cause_reg         = 4'b0;
        tval_reg          = 32'b0;
        memwrite_out_reg  = memwrite;

        if (id_xcpt)
        begin
            xcpt_reg = 1'b1;
            cause_reg = id_cause;
            if (id_irq)
                tval_reg = 32'b0;
            else
            begin
                case (id_cause)
                    4'd2: tval_reg = inst;
                    4'd3: tval_reg = pc;
                    4'd1,
                    4'd12: tval_reg = inst[20] ? (pc + 32'd2) : pc;
                    default: tval_reg = 32'b0;
                endcase
            end
        end
        else if (misaligned)
        begin
            xcpt_reg = 1'b1;
            cause_reg = d_store ? 4'd6 : 4'd4;
            tval_reg = alu_y;
        end
        else if (d_pf)
        begin
            xcpt_reg = 1'b1;
            cause_reg = d_store ? 4'd15 : 4'd13;
            tval_reg = alu_y;
        end
        else if (d_af)
        begin
            xcpt_reg = 1'b1;
            cause_reg = d_store ? 4'd7 : 4'd5;
            tval_reg = alu_y;
        end
        else
        begin
            xcpt_reg = 1'b0;
            cause_reg = 4'b0;
            tval_reg = 32'b0;
        end

        // memwrite_out is cleared when an exception is generated
        if (xcpt_reg)
            memwrite_out_reg = 1'b0;
    end

    // Drive outputs
    assign xcpt          = xcpt_reg;
    assign cause         = cause_reg;
    assign tval          = tval_reg;
    assign memwrite_out  = memwrite_out_reg;

endmodule
