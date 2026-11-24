module line_addrs8 (
    input  wire [31:0] a,
    output wire [255:0] y
);

    wire [26:0] line_addr;
    assign line_addr = a[31:5];

    assign y[31:0]   = {line_addr, 3'd0, 2'b00};
    assign y[63:32]  = {line_addr, 3'd1, 2'b00};
    assign y[95:64]  = {line_addr, 3'd2, 2'b00};
    assign y[127:96] = {line_addr, 3'd3, 2'b00};
    assign y[159:128] = {line_addr, 3'd4, 2'b00};
    assign y[191:160] = {line_addr, 3'd5, 2'b00};
    assign y[223:192] = {line_addr, 3'd6, 2'b00};
    assign y[255:224] = {line_addr, 3'd7, 2'b00};

endmodule
