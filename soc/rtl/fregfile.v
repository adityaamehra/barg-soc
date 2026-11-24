module fregfile (
    input  wire         clk,
    input  wire         we_lo,
    input  wire         we_hi,
    input  wire [4:0]   waddr,
    input  wire [31:0]  wdata_lo,
    input  wire [31:0]  wdata_hi,
    input  wire [4:0]   ra1,
    input  wire [4:0]   ra2,
    input  wire [4:0]   ra3,
    output wire [63:0]  rdata1,
    output wire [63:0]  rdata2,
    output wire [63:0]  rdata3
);

    reg [63:0] mem [0:31];

    // Combinational read: data before the clock edge
    assign rdata1 = mem[ra1];
    assign rdata2 = mem[ra2];
    assign rdata3 = mem[ra3];

    // Synchronous write on rising clock edge
    always @(posedge clk) begin
        if (we_lo || we_hi) begin
            reg [63:0] new_val;
            new_val = mem[waddr];
            if (we_lo) new_val[31:0]   = wdata_lo;
            if (we_hi) new_val[63:32]  = wdata_hi;
            mem[waddr] <= new_val;
        end
    end

endmodule
