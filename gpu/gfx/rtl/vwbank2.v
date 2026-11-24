module vwbank2 (
    input wire clk,
    input wire we,
    input wire [14:0] waddr,
    input wire [15:0] wdata,
    input wire [14:0] raddr,
    output reg [15:0] rdata
);
    localparam DEPTH = 19200;

    reg [15:0] mem [0:DEPTH-1];
    wire [14:0] rindex;
    integer i;

    assign rindex = (raddr < 15'd19200) ? raddr : 15'd0;

    initial begin
        for (i = 0; i < DEPTH; i = i + 1)
            mem[i] = 16'd0;
        rdata = 16'd0;
    end

    always @(posedge clk) begin
        rdata <= mem[rindex];
        if (we && (waddr < 15'd19200))
            mem[waddr] <= wdata;
    end
endmodule
