module wfi_wake2 (
    input  wire        clk,
    input  wire        rst,
    input  wire [31:0] inst,
    input  wire        msip,
    input  wire        mtip,
    input  wire        meip,
    input  wire [11:0] mip_sw,
    input  wire [11:0] mie,
    output wire        hold
);

// ---------------------------------------------------------------------------
// Internal signals
// ---------------------------------------------------------------------------

// pend: combine mip_sw with the three interrupt bits
wire [11:0] pend_bits;
assign pend_bits[3]  = msip;
assign pend_bits[7]  = mtip;
assign pend_bits[11] = meip;
assign pend_bits[0]  = 1'b0;
assign pend_bits[1]  = 1'b0;
assign pend_bits[2]  = 1'b0;
assign pend_bits[4]  = 1'b0;
assign pend_bits[5]  = 1'b0;
assign pend_bits[6]  = 1'b0;
assign pend_bits[8]  = 1'b0;
assign pend_bits[9]  = 1'b0;
assign pend_bits[10] = 1'b0;

wire [11:0] pend;
assign pend = mip_sw | pend_bits;

// wait_on: WFI instruction and no enabled interrupt pending
wire wait_on;
assign wait_on = (inst == 32'h10500073) && ((pend & mie) == 12'b0);

// ---------------------------------------------------------------------------
// Counter
// ---------------------------------------------------------------------------

reg [15:0] cnt;

always @(posedge clk) begin
    if (rst) begin
        cnt <= 16'd0;
    end else begin
        if (wait_on) begin
            if (cnt != 16'hFFFF)
                cnt <= cnt + 16'd1;
            else
                cnt <= cnt; // stay at max
        end else begin
            cnt <= 16'd0;
        end
    end
end

// ---------------------------------------------------------------------------
// Hold output
// ---------------------------------------------------------------------------

assign hold = wait_on && (cnt != 16'hFFFF);

endmodule
