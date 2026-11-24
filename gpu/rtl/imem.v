module imem (
    input clk,
    input [8:0] raddr,
    output reg [31:0] rdata,
    input we,
    input [8:0] waddr,
    input [31:0] wdata
);

    reg [31:0] mem [0:511];
    integer i;

    initial begin
        for (i = 0; i < 512; i = i + 1)
            mem[i] = 32'd0;
    end

    always @(posedge clk) begin
        if (we)
            mem[waddr] <= wdata;
        rdata <= mem[raddr];
    end

endmodule
