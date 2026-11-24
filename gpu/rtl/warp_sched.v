module warp_sched (
    input wire clk,
    input wire rst,
    input wire start,
    input wire enable,
    input wire [3:0] active,
    input wire [3:0] inflight,
    input wire [3:0] waiting,
    output wire fire,
    output wire [1:0] fwid
);

    reg [1:0] ptr;
    wire [3:0] ready;
    wire [1:0] cand0;
    wire [1:0] cand1;
    wire [1:0] cand2;

    assign ready = active & ~inflight & ~waiting;

    assign cand0 = ptr + 2'd1;
    assign cand1 = ptr + 2'd2;
    assign cand2 = ptr + 2'd3;

    assign fire = enable && (|ready);

    assign fwid = fire ? (ready[cand0] ? cand0 :
                          ready[cand1] ? cand1 :
                          ready[cand2] ? cand2 :
                          ready[ptr]   ? ptr   : 2'd0)
                      : 2'd0;

    always @(posedge clk) begin
        if (rst || start)
            ptr <= 2'd3;
        else if (fire)
            ptr <= fwid;
        else
            ptr <= ptr;
    end

endmodule
