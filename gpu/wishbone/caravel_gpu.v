// The GPU core on Caravel's user-project Wishbone port: wb_bridge (BARG-generated) beside the core (top.v).
// The ports are the names Caravel's user_project_wrapper uses, so this module drops in as the user project; the four gpu_*
// outputs are for GPIO pads or the logic analyser. user_irq[0] is `done` and user_irq[1] is `error` (levels: they stay high
// until the next start). Wishbone map (see README, section 7):
//   0x3000_0000 + off   control registers (CTRL 0x00, START_PC 0x04, KARG 0x08, STATUS 0x0C, ERR_PC 0x10, ERR_INFO 0x14)
//   0x3001_0000 + off   instruction memory, 2 KB, write only
//   0x3002_0000 + off   global memory, 8 KB
//   0x3003_0000 + off   shared memory, 4 KB
// Word accesses only: a write with wbs_sel_i not 4'b1111, a misaligned or an unmapped access is acknowledged and dropped (reads 0).
`timescale 1ns/1ps
module caravel_gpu (
    input         wb_clk_i,
    input         wb_rst_i,
    input         wbs_stb_i,
    input         wbs_cyc_i,
    input         wbs_we_i,
    input  [3:0]  wbs_sel_i,
    input  [31:0] wbs_dat_i,
    input  [31:0] wbs_adr_i,
    output        wbs_ack_o,
    output [31:0] wbs_dat_o,
    output [2:0]  user_irq,
    output        gpu_running,
    output        gpu_done,
    output        gpu_error,
    output        gpu_diverged
);
    wire        host_en, host_we, host_rvalid;
    wire [31:0] host_addr, host_wdata, host_rdata;

    wb_bridge u_bridge (
        .clk(wb_clk_i), .rst(wb_rst_i),
        .wb_cyc(wbs_cyc_i), .wb_stb(wbs_stb_i), .wb_we(wbs_we_i), .wb_sel(wbs_sel_i),
        .wb_adr(wbs_adr_i), .wb_dat_i(wbs_dat_i), .wb_ack(wbs_ack_o), .wb_dat_o(wbs_dat_o),
        .host_en(host_en), .host_we(host_we), .host_addr(host_addr), .host_wdata(host_wdata),
        .host_rdata(host_rdata), .host_rvalid(host_rvalid)
    );

    top u_gpu (
        .clk(wb_clk_i), .rst(wb_rst_i),
        .host_en(host_en), .host_we(host_we), .host_addr(host_addr), .host_wdata(host_wdata),
        .host_rdata(host_rdata), .host_rvalid(host_rvalid),
        .running(gpu_running), .done(gpu_done), .error(gpu_error), .diverged(gpu_diverged)
    );

    assign user_irq = {1'b0, gpu_error, gpu_done};
endmodule
