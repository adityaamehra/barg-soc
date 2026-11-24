module vdbank3 (
    input clk,
    input we,
    input [14:0] waddr,
    input [15:0] wdata,
    input [14:0] raddr,
    output reg [15:0] rdata
);
    localparam integer DEPTH = 19200;

    reg [15:0] mem [0:DEPTH-1];
    integer i;

    initial begin
        for (i = 0; i < DEPTH; i = i + 1)
            mem[i] = 16'd0;
        rdata = 16'd0;
    end

    always @(posedge clk) begin
        if (raddr < 15'd19200)
            rdata <= mem[raddr];
        else
            rdata <= 16'd0;

        if (we && (waddr < 15'd19200))
            mem[waddr] <= wdata;
    end
endmodule
