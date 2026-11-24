module vwbank0 (
    input  wire        clk,
    input  wire        we,
    input  wire [14:0] waddr,
    input  wire [15:0] wdata,
    input  wire [14:0] raddr,
    output reg  [15:0] rdata
);

    reg [15:0] mem [0:19199];
    integer i;

    initial begin
        for (i = 0; i < 19200; i = i + 1)
            mem[i] = 16'd0;
    end

    wire wsel = (waddr < 15'd19200);
    wire rsel = (raddr < 15'd19200);

    always @(posedge clk) begin
        if (we && wsel)
            mem[waddr] <= wdata;
        rdata <= rsel ? mem[raddr] : 16'd0;
    end

endmodule
