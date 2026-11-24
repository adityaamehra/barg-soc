module csr_hw (
    input  [31:0] inst,
    input  [2:0]  csrop,
    input  [1:0]  priv,
    input  [5:0]  sel_in,
    input         ill_in,
    output [5:0]  sel_out,
    output        ill_out
);

    wire [11:0] a = inst[31:20];

    wire hw =
        (a == 12'h310) ||
        (a == 12'h30A) ||
        (a == 12'h31A) ||
        (a == 12'h10A) ||
        ((a >= 12'h323) && (a <= 12'h33F)) ||
        ((a >= 12'hB03) && (a <= 12'hB1F)) ||
        ((a >= 12'hB83) && (a <= 12'hB9F)) ||
        ((a >= 12'hC03) && (a <= 12'hC1F)) ||
        ((a >= 12'hC83) && (a <= 12'hC9F));

    wire pmp_a = ((a >= 12'h3A1) && (a <= 12'h3A3));
    wire pmp_b = ((a >= 12'h3B1) && (a <= 12'h3BF));

    reg csr_access;
    reg csr_write;
    always @* begin
        case (csrop)
            3'b000: begin csr_access = 1'b0; csr_write = 1'b0; end
            3'b001: begin csr_access = 1'b1; csr_write = 1'b0; end
            3'b010: begin csr_access = 1'b1; csr_write = 1'b1; end
            3'b011: begin csr_access = 1'b1; csr_write = 1'b1; end
            3'b100: begin csr_access = 1'b1; csr_write = 1'b1; end
            3'b101: begin csr_access = 1'b0; csr_write = 1'b0; end
            3'b110: begin csr_access = 1'b0; csr_write = 1'b0; end
            3'b111: begin csr_access = 1'b0; csr_write = 1'b0; end
        endcase
    end

    wire not_m    = (priv != 2'b11);
    wire readonly = (a[11:10] == 2'b11);
    wire zero_sel = (sel_in == 6'd0);

    wire hw_ill  = (csr_access && not_m) || (csr_write && readonly);
    wire pmp_ill = csr_access && not_m;

    assign sel_out = (zero_sel && hw)    ? 6'd44 :
                     (zero_sel && pmp_a) ? 6'd42 :
                     (zero_sel && pmp_b) ? 6'd43 :
                                           sel_in;

    assign ill_out = (zero_sel && hw)    ? hw_ill  :
                     (zero_sel && pmp_a) ? pmp_ill :
                     (zero_sel && pmp_b) ? pmp_ill :
                                           ill_in;

endmodule
