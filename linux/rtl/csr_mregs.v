module csr_mregs (
    input  wire         clk,
    input  wire         rst,
    input  wire [5:0]   sel,
    input  wire         we,
    input  wire [31:0]  nval,
    input  wire         trap_m,
    input  wire [31:0]  epc,
    input  wire [31:0]  cause_val,
    input  wire [31:0]  tval,
    output reg  [31:0]  mtvec,
    output reg  [31:0]  mscratch,
    output reg  [31:0]  mepc,
    output reg  [31:0]  mcause,
    output reg  [31:0]  mtval,
    output reg  [11:0]  mie,
    output reg  [15:0]  medeleg,
    output reg  [11:0]  mideleg,
    output reg  [2:0]   mcounteren,
    output reg  [11:0]  mip_sw
);

    always @(posedge clk) begin
        if (rst) begin
            mtvec      <= 32'd0;
            mscratch   <= 32'd0;
            mepc       <= 32'd0;
            mcause     <= 32'd0;
            mtval      <= 32'd0;
            mie        <= 12'd0;
            medeleg    <= 16'd0;
            mideleg    <= 12'd0;
            mcounteren <= 3'd0;
            mip_sw     <= 12'd0;
        end else if (trap_m) begin
            mepc   <= epc & 32'hFFFFFFFE;
            mcause <= cause_val;
            mtval  <= tval;
        end else if (we) begin
            case (sel)
                6'd3:   medeleg    <= nval[15:0] & 16'hB3FF;
                6'd4:   mideleg    <= nval[11:0] & 12'h222;
                6'd5:   mie        <= nval[11:0] & 12'hAAA;
                6'd6:   mtvec      <= nval & 32'hFFFFFFFD;
                6'd7:   mcounteren <= nval[2:0];
                6'd8:   mscratch   <= nval;
                6'd9:   mepc       <= nval & 32'hFFFFFFFE;
                6'd10:  mcause     <= nval;
                6'd11:  mtval      <= nval;
                6'd12:  mip_sw     <= (mip_sw & 12'h200) | (nval[11:0] & 12'h022);
                6'd28:  mie        <= (mie & ~mideleg) | (nval[11:0] & mideleg & 12'h222);
                6'd35:  mip_sw     <= (mip_sw & ~(mideleg & 12'h2)) | (nval[11:0] & mideleg & 12'h2);
                default: ;
            endcase
        end
    end

endmodule
