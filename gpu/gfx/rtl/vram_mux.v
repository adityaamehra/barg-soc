module vram_mux (
    input running,
    input v_we0,
    input v_we1,
    input v_we2,
    input v_we3,
    input [14:0] v_waddr,
    input [15:0] v_wdata_lo,
    input [15:0] v_wdata_hi,
    input r_we0,
    input r_we1,
    input r_we2,
    input r_we3,
    input [14:0] r_waddr0,
    input [14:0] r_waddr1,
    input [14:0] r_waddr2,
    input [14:0] r_waddr3,
    input [15:0] r_wdata0,
    input [15:0] r_wdata1,
    input [15:0] r_wdata2,
    input [15:0] r_wdata3,
    output m_we0,
    output m_we1,
    output m_we2,
    output m_we3,
    output [14:0] m_waddr0,
    output [14:0] m_waddr1,
    output [14:0] m_waddr2,
    output [14:0] m_waddr3,
    output [15:0] m_wdata0,
    output [15:0] m_wdata1,
    output [15:0] m_wdata2,
    output [15:0] m_wdata3
);

    assign m_we0 = running ? r_we0 : v_we0;
    assign m_we1 = running ? r_we1 : v_we1;
    assign m_we2 = running ? r_we2 : v_we2;
    assign m_we3 = running ? r_we3 : v_we3;

    assign m_waddr0 = running ? r_waddr0 : v_waddr;
    assign m_waddr1 = running ? r_waddr1 : v_waddr;
    assign m_waddr2 = running ? r_waddr2 : v_waddr;
    assign m_waddr3 = running ? r_waddr3 : v_waddr;

    assign m_wdata0 = running ? r_wdata0 : v_wdata_lo;
    assign m_wdata1 = running ? r_wdata1 : v_wdata_hi;
    assign m_wdata2 = running ? r_wdata2 : v_wdata_lo;
    assign m_wdata3 = running ? r_wdata3 : v_wdata_hi;

endmodule
