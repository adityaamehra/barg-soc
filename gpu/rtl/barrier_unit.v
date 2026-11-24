module barrier_unit (
    input  wire       clk,
    input  wire       rst,
    input  wire       clear_all,
    input  wire       en,
    input  wire [1:0] wid,
    input  wire [1:0] bar_id,
    input  wire [2:0] bar_count,
    output reg  [3:0] waiting
);

    reg [3:0] arrived [0:3];
    wire [3:0] m;
    wire [2:0] cnt;
    integer i;

    assign m = arrived[bar_id] | (4'b0001 << wid);

    assign cnt = {2'b00, m[0]}
               + {2'b00, m[1]}
               + {2'b00, m[2]}
               + {2'b00, m[3]};

    always @(posedge clk) begin
        if (rst || clear_all) begin
            for (i = 0; i < 4; i = i + 1) begin
                arrived[i] <= 4'b0000;
            end
            waiting <= 4'b0000;
        end else if (en) begin
            if (cnt >= bar_count) begin
                arrived[bar_id] <= 4'b0000;
                waiting <= waiting & ~m;
            end else begin
                arrived[bar_id] <= m;
                waiting <= waiting | (4'b0001 << wid);
            end
        end
    end

endmodule
