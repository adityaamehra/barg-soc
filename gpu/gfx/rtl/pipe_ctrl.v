module pipe_ctrl (
    input  wire        running,
    input  wire        dx_valid,
    input  wire [2:0]  unit,
    input  wire        div_ready,
    input  wire        lsu_ready,
    input  wire [31:0] sel_pc,
    input  wire [31:0] sf_pc,
    output wire        stall,
    output wire        advance,
    output wire        sched_en,
    output wire [8:0]  fetch_idx,
    input  wire        g_busy
);
    wire div_wait = dx_valid & (unit == 3'b010) & ~div_ready;
    wire lsu_wait = dx_valid & (unit == 3'b011) & ~lsu_ready;
    wire x_busy = div_wait | lsu_wait | g_busy;

    assign stall    = x_busy;
    assign advance  = dx_valid & ~x_busy;
    assign sched_en = running & ~x_busy;
    assign fetch_idx = x_busy ? sf_pc[10:2] : sel_pc[10:2];

endmodule
