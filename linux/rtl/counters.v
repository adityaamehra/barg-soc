module counters (
    input  wire         clk,
    input  wire         rst,
    input  wire         retire,
    input  wire         we,
    input  wire [5:0]   sel,
    input  wire [31:0]  nval,
    output wire [63:0]  mcycle,
    output wire [63:0]  minstret
);

    reg [63:0] mcycle_reg, minstret_reg;

    wire we_mcycle   = we && (sel == 6'd13 || sel == 6'd15);
    wire we_minstret = we && (sel == 6'd14 || sel == 6'd16);

    wire [63:0] mcycle_next   = we_mcycle   ? (sel == 6'd13 ? {mcycle_reg[63:32], nval} : {nval, mcycle_reg[31:0]}) : mcycle_reg + 1;
    wire [63:0] minstret_next = we_minstret ? (sel == 6'd14 ? {minstret_reg[63:32], nval} : {nval, minstret_reg[31:0]}) : minstret_reg + (retire ? 1 : 0);

    always @(posedge clk) begin
        if (rst) begin
            mcycle_reg   <= 64'd0;
            minstret_reg <= 64'd0;
        end else begin
            mcycle_reg   <= mcycle_next;
            minstret_reg <= minstret_next;
        end
    end

    assign mcycle   = mcycle_reg;
    assign minstret = minstret_reg;

endmodule
