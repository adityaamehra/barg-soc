module vwbank3 (
    input clk,
    input we,
    input [14:0] waddr,
    input [15:0] wdata,
    input [14:0] raddr,
    output reg [15:0] rdata
);
    reg [15:0] mem [0:19199];
    integer i;
    wire [15:0] rdata_next;

    initial begin
        for (i = 0; i < 19200; i = i + 1) begin
            mem[i] = 16'h0000;
        end
        rdata = 16'h0000;
    end

    assign rdata_next = (raddr < 15'd19200) ? mem[raddr] : 16'h0000;

    always @(posedge clk) begin
        if (we && (waddr < 15'd19200)) begin
            mem[waddr] <= wdata;
        end
        rdata <= rdata_next;
    end
endmodule
