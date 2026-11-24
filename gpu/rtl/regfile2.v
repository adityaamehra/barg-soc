module regfile2(
    input clk,
    input [6:0] raddr,
    output [31:0] rdata,
    input [6:0] raddr2,
    output [31:0] rdata2,
    input we,
    input [6:0] waddr,
    input [31:0] wdata
);

    reg [31:0] mem [0:127];
    integer i;

    initial begin
        for (i = 0; i < 128; i = i + 1)
            mem[i] = 32'd0;
    end

    assign rdata = mem[raddr];
    assign rdata2 = mem[raddr2];

    always @(posedge clk) begin
        if (we)
            mem[waddr] <= wdata;
    end

endmodule
