module postw (
    input  clk,
    input  rst,
    input  start,
    input  we,
    input  amo,
    input  wdone,
    input  g0,
    input  g1,
    input  g2,
    input  g3,
    input  b0,
    input  b1,
    input  b2,
    input  b3,
    output wdone_o,
    output go0,
    output go1,
    output go2,
    output go3
);

    // Internal signals
    wire posted;
    reg  pst;

    // posted = start & we & ~amo
    assign posted = start & we & ~amo;

    // pst register: synchronous reset
    always @(posedge clk) begin
        if (rst) begin
            pst <= 1'b0;
        end else begin
            if (posted) begin
                pst <= 1'b1;
            end else if (pst && wdone) begin
                pst <= 1'b0;
            end
            // else keep current value
        end
    end

    // Outputs
    assign wdone_o = (wdone & ~pst) | posted;

    assign go0 = (g0 & ~pst) | (posted & b0);
    assign go1 = (g1 & ~pst) | (posted & b1);
    assign go2 = (g2 & ~pst) | (posted & b2);
    assign go3 = (g3 & ~pst) | (posted & b3);

endmodule
