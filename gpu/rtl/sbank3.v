module sbank3(
    input  wire        clk,
    input  wire [7:0]  addr,
    input  wire        we,
    input  wire [31:0] wdata,
    input  wire [3:0]  be,
    output wire [31:0] rdata
);

    reg [31:0] mem [0:255];
    reg [31:0] rdata_reg;
    integer i;

    initial begin
        for (i = 0; i < 256; i = i + 1)
            mem[i] = 32'd0;
        rdata_reg = 32'd0;
    end

    always @(posedge clk) begin
        rdata_reg <= mem[addr];
        if (we) begin
            if (be[0]) mem[addr][7:0]   <= wdata[7:0];
            if (be[1]) mem[addr][15:8]  <= wdata[15:8];
            if (be[2]) mem[addr][23:16] <= wdata[23:16];
            if (be[3]) mem[addr][31:24] <= wdata[31:24];
        end
    end

    assign rdata = rdata_reg;

endmodule
