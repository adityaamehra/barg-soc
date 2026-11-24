module z_mux (
    input running,
    input zh_we0,
    input zh_we1,
    input zh_we2,
    input zh_we3,
    input [14:0] zh_waddr,
    input [15:0] zh_wdata_lo,
    input [15:0] zh_wdata_hi,
    input zw_we0,
    input zw_we1,
    input zw_we2,
    input zw_we3,
    input [14:0] zw_waddr0,
    input [14:0] zw_waddr1,
    input [14:0] zw_waddr2,
    input [14:0] zw_waddr3,
    input [15:0] zw_wdata0,
    input [15:0] zw_wdata1,
    input [15:0] zw_wdata2,
    input [15:0] zw_wdata3,
    output mz_we0,
    output mz_we1,
    output mz_we2,
    output mz_we3,
    output [14:0] mz_waddr0,
    output [14:0] mz_waddr1,
    output [14:0] mz_waddr2,
    output [14:0] mz_waddr3,
    output [15:0] mz_wdata0,
    output [15:0] mz_wdata1,
    output [15:0] mz_wdata2,
    output [15:0] mz_wdata3
);

    assign mz_we0 = running ? zw_we0 : zh_we0;
    assign mz_we1 = running ? zw_we1 : zh_we1;
    assign mz_we2 = running ? zw_we2 : zh_we2;
    assign mz_we3 = running ? zw_we3 : zh_we3;

    assign mz_waddr0 = running ? zw_waddr0 : zh_waddr;
    assign mz_waddr1 = running ? zw_waddr1 : zh_waddr;
    assign mz_waddr2 = running ? zw_waddr2 : zh_waddr;
    assign mz_waddr3 = running ? zw_waddr3 : zh_waddr;

    assign mz_wdata0 = running ? zw_wdata0 : zh_wdata_lo;
    assign mz_wdata1 = running ? zw_wdata1 : zh_wdata_hi;
    assign mz_wdata2 = running ? zw_wdata2 : zh_wdata_lo;
    assign mz_wdata3 = running ? zw_wdata3 : zh_wdata_hi;

endmodule
