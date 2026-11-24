module wfi_wake (
    input  wire [31:0] inst,
    input  wire        msip,
    input  wire        mtip,
    input  wire        meip,
    input  wire [11:0] mip_sw,
    input  wire [11:0] mie,
    output wire        hold
);

// Construct the pending interrupt vector
wire [11:0] pend;
assign pend = mip_sw | {meip, 3'd0, mtip, 3'd0, msip, 3'd0};

// Determine if the instruction is WFI (0x10500073) and no enabled interrupt is pending
assign hold = (inst == 32'h10500073) && ((pend & mie) == 12'd0);

endmodule
