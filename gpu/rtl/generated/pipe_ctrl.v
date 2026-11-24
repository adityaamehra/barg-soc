module pipe_ctrl (
    input wire running,
    input wire dx_valid,
    input wire [2:0] unit,
    input wire div_ready,
    input wire lsu_ready,
    input wire [31:0] sel_pc,
    input wire [31:0] sf_pc,
    output wire stall,
    output wire advance,
    output wire sched_en,
    output wire [8:0] fetch_idx
);

    reg x_busy;

    always @* begin
        x_busy = 1'b0;
        if (dx_valid) begin
            case (unit)
                3'b010: x_busy = ~div_ready;
                3'b011: x_busy = ~lsu_ready;
                default: x_busy = 1'b0;
            endcase
        end
    end

    assign stall    = x_busy;
    assign advance  = dx_valid & ~x_busy;
    assign sched_en = running & ~x_busy;

    assign fetch_idx = x_busy ? sf_pc[10:2] : sel_pc[10:2];

endmodule
