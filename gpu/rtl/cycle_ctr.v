module cycle_ctr (
    input  wire        clk,
    input  wire        rst,
    input  wire        enable,
    output wire [47:0] count
);

    reg [47:0] count_r;

    always @(posedge clk) begin
        if (rst)
            count_r <= 48'd0;
        else if (enable)
            count_r <= count_r + 48'd1;
    end

    assign count = count_r;

endmodule
