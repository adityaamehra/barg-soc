module vdbank1 (
    input clk,
    input we,
    input [14:0] waddr,
    input [15:0] wdata,
    input [14:0] raddr,
    output reg [15:0] rdata
);

    reg [15:0] mem [0:19199];
    integer i;

    wire [14:0] rindex;
    wire [15:0] rdata_next;

    initial begin
        for (i = 0; i < 19200; i = i + 1)
            mem[i] = 16'd0;
    end

    assign rindex = (raddr < 15'd19200) ? raddr : 15'd0;
    assign rdata_next = (raddr < 15'd19200) ? mem[rindex] : 16'd0;

    always @(posedge clk) begin
        if (we && (waddr < 15'd19200))
            mem[waddr] <= wdata;
        rdata <= rdata_next;
    end

endmodule
