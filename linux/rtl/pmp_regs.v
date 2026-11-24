module pmp_regs (
    input  wire        clk,
    input  wire        rst,
    input  wire        we,
    input  wire [5:0]  sel,
    input  wire [31:0] nval,
    output reg  [31:0] pmpcfg0,
    output reg  [31:0] pmpaddr0
);

    always @(posedge clk) begin
        if (rst) begin
            pmpcfg0  <= 32'd0;
            pmpaddr0 <= 32'd0;
        end else begin
            if (we) begin
                case (sel)
                    6'd42: pmpcfg0  <= nval;
                    6'd43: pmpaddr0 <= nval;
                    default: begin
                        pmpcfg0  <= pmpcfg0;
                        pmpaddr0 <= pmpaddr0;
                    end
                endcase
            end
        end
    end

endmodule
