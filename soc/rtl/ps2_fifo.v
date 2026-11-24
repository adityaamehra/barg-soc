module ps2_fifo (
    input  clk,
    input  rst,
    input  pop,
    input  push,
    input  [7:0] din,
    output [7:0] head,
    output [3:0] count
);

// Internal registers
reg [7:0] q0, q1, q2, q3, q4, q5, q6, q7;
reg [3:0] cnt;

// Reset: synchronous
always @(posedge clk) begin
    if (rst) begin
        q0 <= 8'd0; q1 <= 8'd0; q2 <= 8'd0; q3 <= 8'd0;
        q4 <= 8'd0; q5 <= 8'd0; q6 <= 8'd0; q7 <= 8'd0;
        cnt <= 4'd0;
    end else begin
        // Determine next count
        reg [3:0] next_cnt;
        reg [7:0] next_q0, next_q1, next_q2, next_q3;
        reg [7:0] next_q4, next_q5, next_q6, next_q7;

        // Default assignments
        next_q0 = q0; next_q1 = q1; next_q2 = q2; next_q3 = q3;
        next_q4 = q4; next_q5 = q5; next_q6 = q6; next_q7 = q7;
        next_cnt = cnt;

        // Handle pop first
        if (pop && (cnt != 0)) begin
            next_q0 = q1;
            next_q1 = q2;
            next_q2 = q3;
            next_q3 = q4;
            next_q4 = q5;
            next_q5 = q6;
            next_q6 = q7;
            next_q7 = 8'd0;
            next_cnt = cnt - 4'd1;
        end

        // Handle push after pop
        if (push && (next_cnt < 4'd8)) begin
        case (next_cnt)
            4'd0: next_q0 = din;
            4'd1: next_q1 = din;
            4'd2: next_q2 = din;
            4'd3: next_q3 = din;
            4'd4: next_q4 = din;
            4'd5: next_q5 = din;
            4'd6: next_q6 = din;
            4'd7: next_q7 = din;
            default: ; // no change for out-of-range values
        endcase
            next_cnt = next_cnt + 4'd1;
        end

        // Commit next state
        q0 <= next_q0; q1 <= next_q1; q2 <= next_q2; q3 <= next_q3;
        q4 <= next_q4; q5 <= next_q5; q6 <= next_q6; q7 <= next_q7;
        cnt <= next_cnt;
    end
end

// Combinational outputs
assign head  = (cnt != 0) ? q0 : 8'd0;
assign count = cnt;

endmodule
