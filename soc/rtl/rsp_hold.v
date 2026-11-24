module rsp_hold (
    input  wire         clk,
    input  wire         rst,
    input  wire         done,
    input  wire [255:0] line,
    output wire [255:0] data,
    output wire [31:0]  word
);

    reg [255:0] held;

    always @(posedge clk) begin
        if (rst) begin
            held <= 256'd0;
        end else if (done) begin
            held <= line;
        end
    end

    assign data = done ? line : held;
    assign word = data[31:0];

endmodule
