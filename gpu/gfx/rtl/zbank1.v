module zbank1 (
    input clk,
    input we,
    input [14:0] waddr,
    input [15:0] wdata,
    input [14:0] raddr,
    output reg [15:0] rdata
);

    reg [15:0] mem [0:19199];

    integer i;
    initial begin
        for (i = 0; i < 19200; i = i + 1)
            mem[i] = 16'd0;
    end

    always @(posedge clk) begin
        if (we && (waddr < 15'd19200))
            mem[waddr] <= wdata;

        if (raddr < 15'd19200)
            rdata <= mem[raddr];
        else
            rdata <= 16'd0;
    end

endmodule
