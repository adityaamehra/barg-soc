module i2c_regs (
    input  clk,
    input  rst,
    input  we,
    input  [31:0] addr,
    input  [31:0] wdata,
    input  cmd_ready,
    input  rsp_valid,
    input  [7:0] rsp_data,
    input  rsp_nack,
    input  rsp_arb_lost,
    output [31:0] rdata,
    output cmd_valid,
    output [1:0] cmd_op,
    output cmd_start,
    output cmd_stop,
    output cmd_nack,
    output [7:0] cmd_data,
    output irq
);

// Internal registers
reg  [7:0] last;
reg        done;
reg        busy;
reg        nack;
reg        arb;
reg        ien;

// Command signals (combinational)
assign cmd_valid = we && (addr[4:2] == 3'b000) && cmd_ready;
assign cmd_op    = wdata[12:11];
assign cmd_start = wdata[8];
assign cmd_stop  = wdata[9];
assign cmd_nack  = wdata[10];
assign cmd_data  = wdata[7:0];

// IRQ generation
assign irq = done & ien;

// Read data (combinational)
assign rdata = (addr[4:2] == 3'b000) ? {24'b0, last} :
               (addr[4:2] == 3'b001) ? {28'b0, arb, nack, done, busy} :
               (addr[4:2] == 3'b010) ? 32'b0 :
               (addr[4:2] == 3'b011) ? {31'b0, ien} :
               32'b0;

// Sequential logic
always @(posedge clk) begin
    if (rst) begin
        last <= 8'b0;
        done <= 1'b0;
        busy <= 1'b0;
        nack <= 1'b0;
        arb  <= 1'b0;
        ien  <= 1'b0;
    end else begin
        // Update interrupt enable
        if (we && (addr[4:2] == 3'b011))
            ien <= wdata[0];

        // Clear status bits on clear write (when not busy)
        if (!rsp_valid && we && (addr[4:2] == 3'b001) && wdata[1])
            begin
                done <= 1'b0;
                nack <= 1'b0;
                arb  <= 1'b0;
            end

        // Response handling (priority over command)
        if (rsp_valid) begin
            busy <= 1'b0;
            done <= 1'b1;
            last <= rsp_data;
            nack <= rsp_nack;
            arb  <= rsp_arb_lost;
        end
        // Command handling
        else if (cmd_valid) begin
            busy <= 1'b1;
        end
    end
end

endmodule
