module vram_rmux (
    input running,
    input [14:0] vw_raddr,
    input [14:0] r_raddr0,
    input [14:0] r_raddr1,
    input [14:0] r_raddr2,
    input [14:0] r_raddr3,
    output [14:0] m_raddr0,
    output [14:0] m_raddr1,
    output [14:0] m_raddr2,
    output [14:0] m_raddr3
);

    assign m_raddr0 = running ? r_raddr0 : vw_raddr;
    assign m_raddr1 = running ? r_raddr1 : vw_raddr;
    assign m_raddr2 = running ? r_raddr2 : vw_raddr;
    assign m_raddr3 = running ? r_raddr3 : vw_raddr;

endmodule
