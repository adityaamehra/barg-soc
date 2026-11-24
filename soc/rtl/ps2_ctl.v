module ps2_ctl(
    input  clk,
    input  rst,
    input  we,
    input  re_pulse,
    input  [31:0] addr,
    input  [31:0] wdata,
    input  [7:0]  head,
    input  [3:0]  count,
    input  tx_busy,
    input  tx_done,
    input  tx_err,
    output [31:0] rdata,
    output        pop,
    output        tx_start,
    output [7:0]  tx_data,
    output        irq
);

    // Internal registers
    reg re_reg;
    reg ce_reg;

    // Reset and register updates
    always @(posedge clk) begin
        if (rst) begin
            re_reg <= 1'b0;
            ce_reg <= 1'b0;
        end else begin
            // Write to CONTROL register (bit 2 of addr == 1)
            if (we && addr[2]) begin
                re_reg <= wdata[0];
                ce_reg <= 1'b0;
            end
            // Command error from transmitter
            if (tx_done && tx_err) begin
                ce_reg <= 1'b1;
            end
        end
    end

    // pop is combinational: load when re_pulse and accessing DATA register
    assign pop = re_pulse && !addr[2];

    // tx_start combinational: start when we, accessing DATA, and transmitter idle
    assign tx_start = we && !addr[2] && !tx_busy;

    // tx_data always the lower 8 bits of wdata
    assign tx_data = wdata[7:0];

    // rdata combinational
    assign rdata = addr[2] ?
                   {21'd0, ce_reg, 1'b0, (re_reg & (count != 4'd0)), 7'd0, re_reg}
                   :
                   {12'd0, count[3:0], (count != 4'd0), 7'd0, head};

    // irq combinational: re_reg && count != 0
    assign irq = re_reg && (count != 4'd0);

endmodule
