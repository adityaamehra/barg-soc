module px_pick(
    input  [31:0] word,
    input         half,
    input         de,
    output [4:0]  r,
    output [5:0]  g,
    output [4:0]  b
);

    // Select the 16-bit pixel based on 'half'
    wire [15:0] pixel = half ? word[31:16] : word[15:0];

    // Extract RGB565 components
    assign r = de ? pixel[15:11] : 5'd0;
    assign g = de ? pixel[10:5]  : 6'd0;
    assign b = de ? pixel[4:0]   : 5'd0;

endmodule
