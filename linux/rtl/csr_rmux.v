module csr_rmux (
    input  wire [5:0]   sel,
    input  wire [31:0]  mstatus,
    input  wire [15:0]  medeleg,
    input  wire [11:0]  mideleg,
    input  wire [11:0]  mie,
    input  wire [31:0]  mtvec,
    input  wire [2:0]   mcounteren,
    input  wire [31:0]  mscratch,
    input  wire [31:0]  mepc,
    input  wire [31:0]  mcause,
    input  wire [31:0]  mtval,
    input  wire [11:0]  mip,
    input  wire [63:0]  mcycle,
    input  wire [63:0]  minstret,
    input  wire [63:0]  mtime,
    input  wire [1:0]   hartid,
    input  wire [31:0]  stvec,
    input  wire [2:0]   scounteren,
    input  wire [31:0]  sscratch,
    input  wire [31:0]  sepc,
    input  wire [31:0]  scause,
    input  wire [31:0]  stval,
    input  wire [31:0]  satp,
    input  wire [31:0]  pmpcfg0,
    input  wire [31:0]  pmpaddr0,
    output reg  [31:0]  rdata
);

always @* begin
    rdata = 32'd0;
    case (sel)
        6'd1:   rdata = mstatus;
        6'd2:   rdata = 32'h40141105;
        6'd3:   rdata = {16'd0, medeleg};
        6'd4:   rdata = {20'd0, mideleg};
        6'd5:   rdata = {20'd0, mie};
        6'd6:   rdata = mtvec;
        6'd7:   rdata = {29'd0, mcounteren};
        6'd8:   rdata = mscratch;
        6'd9:   rdata = mepc;
        6'd10:  rdata = mcause;
        6'd11:  rdata = mtval;
        6'd12:  rdata = {20'd0, mip};
        6'd13:  rdata = mcycle[31:0];
        6'd14:  rdata = minstret[31:0];
        6'd15:  rdata = mcycle[63:32];
        6'd16:  rdata = minstret[63:32];
        6'd17:  rdata = mcycle[31:0];
        6'd18:  rdata = mtime[31:0];
        6'd19:  rdata = minstret[31:0];
        6'd20:  rdata = mcycle[63:32];
        6'd21:  rdata = mtime[63:32];
        6'd22:  rdata = minstret[63:32];
        6'd23:  rdata = 32'd0;
        6'd24:  rdata = 32'd0;
        6'd25:  rdata = 32'd0;
        6'd26:  rdata = {30'd0, hartid};
        6'd27:  rdata = mstatus & 32'h000C0122;
        6'd28:  rdata = {20'd0, (mie & mideleg)};
        6'd29:  rdata = stvec;
        6'd30:  rdata = {29'd0, scounteren};
        6'd31:  rdata = sscratch;
        6'd32:  rdata = sepc;
        6'd33:  rdata = scause;
        6'd34:  rdata = stval;
        6'd35:  rdata = {20'd0, (mip & mideleg)};
        6'd36:  rdata = satp;
        6'd37:  rdata = 32'd0;
        6'd38:  rdata = 32'd0;
        6'd39:  rdata = 32'd0;
        6'd40:  rdata = 32'd0;
        6'd41:  rdata = 32'd0;
        6'd42:  rdata = pmpcfg0;
        6'd43:  rdata = pmpaddr0;
        default: rdata = 32'd0;
    endcase
end

endmodule
