module tbank23 (
    input  wire        clk,
    input  wire        we,
    input  wire [7:0]  waddr,
    input  wire [15:0] wdata,
    input  wire [7:0]  raddr,
    output reg  [15:0] rdata
);

    reg [15:0] mem [0:255];

    integer i;
    initial begin
        for (i = 0; i < 256; i = i + 1)
            mem[i] = 16'd0;
    end

    always @(posedge clk) begin
        if (we)
            mem[waddr] <= wdata;
        rdata <= mem[raddr];
    end

endmodule
