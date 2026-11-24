module bp_pipe (
    input  wire         clk,
    input  wire         rst,
    input  wire         stall_if,
    input  wire         flush_if,
    input  wire         stall_id,
    input  wire         flush_id,
    input  wire         pt_if,
    input  wire [31:0]  ptarget_if,
    input  wire [7:0]   pidx_if,
    output reg          pt_ex,
    output reg [31:0]   ptarget_ex,
    output reg [7:0]    pidx_ex
);

    reg         pt_id;
    reg [31:0]  ptarget_id;
    reg [7:0]   pidx_id;

    always @(posedge clk) begin
        if (rst || flush_if) begin
            pt_id      <= 1'b0;
            ptarget_id <= 32'd0;
            pidx_id    <= 8'd0;
        end else if (!stall_if) begin
            pt_id      <= pt_if;
            ptarget_id <= ptarget_if;
            pidx_id    <= pidx_if;
        end
    end

    always @(posedge clk) begin
        if (rst || flush_id) begin
            pt_ex      <= 1'b0;
            ptarget_ex <= 32'd0;
            pidx_ex    <= 8'd0;
        end else if (!stall_id) begin
            pt_ex      <= pt_id;
            ptarget_ex <= ptarget_id;
            pidx_ex    <= pidx_id;
        end
    end

endmodule
