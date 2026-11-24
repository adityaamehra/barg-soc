module fp_csr (
    input  wire         clk,
    input  wire         rst,
    input  wire [31:0]  inst,
    input  wire [2:0]   csrop,
    input  wire         csr_we,
    input  wire [31:0]  nval,
    input  wire [4:0]   flags_set,
    input  wire         dirty_set,
    input  wire [31:0]  rdata_in,
    input  wire         illegal_in,
    output reg  [1:0]   fs,
    output reg  [2:0]   frm,
    output reg  [31:0]  rdata_out,
    output reg          illegal_out
);

    reg [4:0] fflags;

    wire [11:0] addr = inst[31:20];
    wire        csr_access = (csrop == 3'b001) || (csrop == 3'b010) || (csrop == 3'b011) || (csrop == 3'b100);

    always @* begin
        rdata_out  = rdata_in;
        illegal_out = illegal_in;

        case (addr)
            12'h001: rdata_out = {27'd0, fflags};
            12'h002: rdata_out = {29'd0, frm};
            12'h003: rdata_out = {24'd0, frm, fflags};
            12'h300, 12'h100: begin
                rdata_out = rdata_in;
                rdata_out[14:13] = fs;
                if (fs == 2'b11) rdata_out[31] = 1'b1;
            end
            12'h301: begin
                rdata_out = rdata_in;
                rdata_out[3] = 1'b1;
                rdata_out[5] = 1'b1;
            end
            default: rdata_out = rdata_in;
        endcase

        if (csr_access && (addr == 12'h001 || addr == 12'h002 || addr == 12'h003)) begin
            illegal_out = (fs == 2'b00);
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            fflags <= 5'd0;
            frm    <= 3'd0;
            fs     <= 2'd0;
        end else begin
            if (csr_we) begin
                case (addr)
                    12'h001: begin
                        fflags <= nval[4:0];
                        fs     <= 2'b11;
                    end
                    12'h002: begin
                        frm    <= nval[2:0];
                        fs     <= 2'b11;
                    end
                    12'h003: begin
                        frm    <= nval[7:5];
                        fflags <= nval[4:0];
                        fs     <= 2'b11;
                    end
                    12'h300, 12'h100: begin
                        fs <= nval[14:13];
                    end
                    default: ;
                endcase
            end else begin
                fflags <= fflags | flags_set;
                if (dirty_set) fs <= 2'b11;
            end
        end
    end

endmodule
