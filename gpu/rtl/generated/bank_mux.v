module bank_mux (
    input  wire         running,
    input  wire [3:0]   g_en,
    input  wire [3:0]   g_we,
    input  wire [35:0]  g_addr,
    input  wire [127:0] g_wdata,
    input  wire [15:0]  g_be,
    input  wire [3:0]   s_en,
    input  wire [3:0]   s_we,
    input  wire [31:0]  s_addr,
    input  wire [127:0] s_wdata,
    input  wire [15:0]  s_be,
    input  wire         host_en,
    input  wire         host_we,
    input  wire [31:0]  host_addr,
    input  wire [31:0]  host_wdata,
    input  wire [31:0]  gb0_rdata,
    input  wire [31:0]  gb1_rdata,
    input  wire [31:0]  gb2_rdata,
    input  wire [31:0]  gb3_rdata,
    input  wire [31:0]  sb0_rdata,
    input  wire [31:0]  sb1_rdata,
    input  wire [31:0]  sb2_rdata,
    input  wire [31:0]  sb3_rdata,
    output wire         gb0_we,
    output wire [8:0]   gb0_addr,
    output wire [31:0]  gb0_wdata,
    output wire [3:0]   gb0_be,
    output wire         gb1_we,
    output wire [8:0]   gb1_addr,
    output wire [31:0]  gb1_wdata,
    output wire [3:0]   gb1_be,
    output wire         gb2_we,
    output wire [8:0]   gb2_addr,
    output wire [31:0]  gb2_wdata,
    output wire [3:0]   gb2_be,
    output wire         gb3_we,
    output wire [8:0]   gb3_addr,
    output wire [31:0]  gb3_wdata,
    output wire [3:0]   gb3_be,
    output wire         sb0_we,
    output wire [7:0]   sb0_addr,
    output wire [31:0]  sb0_wdata,
    output wire [3:0]   sb0_be,
    output wire         sb1_we,
    output wire [7:0]   sb1_addr,
    output wire [31:0]  sb1_wdata,
    output wire [3:0]   sb1_be,
    output wire         sb2_we,
    output wire [7:0]   sb2_addr,
    output wire [31:0]  sb2_wdata,
    output wire [3:0]   sb2_be,
    output wire         sb3_we,
    output wire [7:0]   sb3_addr,
    output wire [31:0]  sb3_wdata,
    output wire [3:0]   sb3_be,
    output wire         imem_we,
    output wire [8:0]   imem_waddr,
    output wire [31:0]  imem_wdata,
    output wire [127:0] g_rdata,
    output wire [127:0] s_rdata
);

    // Host address decode
    wire host_imem = (host_addr[31:11] == 21'd0);
    wire host_gmem = (host_addr[31:13] == 19'h08000);
    wire host_smem = (host_addr[31:12] == 20'h20000);

    wire [1:0] host_bank = host_addr[3:2];
    wire host_gwe = host_en & host_we;
    wire [8:0] host_gaddr = (host_addr - 32'h1000_0000) >> 4;
    wire [7:0] host_saddr = (host_addr - 32'h2000_0000) >> 4;

    // Global banks
    assign gb0_we    = running ? (g_en[0] & g_we[0]) : (host_gmem & host_gwe & (host_bank == 2'd0));
    assign gb0_addr  = running ? g_addr[8:0]   : host_gaddr;
    assign gb0_wdata = running ? g_wdata[31:0] : host_wdata;
    assign gb0_be    = running ? g_be[3:0]     : 4'hF;

    assign gb1_we    = running ? (g_en[1] & g_we[1]) : (host_gmem & host_gwe & (host_bank == 2'd1));
    assign gb1_addr  = running ? g_addr[17:9]  : host_gaddr;
    assign gb1_wdata = running ? g_wdata[63:32] : host_wdata;
    assign gb1_be    = running ? g_be[7:4]     : 4'hF;

    assign gb2_we    = running ? (g_en[2] & g_we[2]) : (host_gmem & host_gwe & (host_bank == 2'd2));
    assign gb2_addr  = running ? g_addr[26:18] : host_gaddr;
    assign gb2_wdata = running ? g_wdata[95:64] : host_wdata;
    assign gb2_be    = running ? g_be[11:8]    : 4'hF;

    assign gb3_we    = running ? (g_en[3] & g_we[3]) : (host_gmem & host_gwe & (host_bank == 2'd3));
    assign gb3_addr  = running ? g_addr[35:27] : host_gaddr;
    assign gb3_wdata = running ? g_wdata[127:96] : host_wdata;
    assign gb3_be    = running ? g_be[15:12]   : 4'hF;

    // Shared banks
    assign sb0_we    = running ? (s_en[0] & s_we[0]) : (host_smem & host_gwe & (host_bank == 2'd0));
    assign sb0_addr  = running ? s_addr[7:0]   : host_saddr;
    assign sb0_wdata = running ? s_wdata[31:0] : host_wdata;
    assign sb0_be    = running ? s_be[3:0]     : 4'hF;

    assign sb1_we    = running ? (s_en[1] & s_we[1]) : (host_smem & host_gwe & (host_bank == 2'd1));
    assign sb1_addr  = running ? s_addr[15:8]  : host_saddr;
    assign sb1_wdata = running ? s_wdata[63:32] : host_wdata;
    assign sb1_be    = running ? s_be[7:4]     : 4'hF;

    assign sb2_we    = running ? (s_en[2] & s_we[2]) : (host_smem & host_gwe & (host_bank == 2'd2));
    assign sb2_addr  = running ? s_addr[23:16] : host_saddr;
    assign sb2_wdata = running ? s_wdata[95:64] : host_wdata;
    assign sb2_be    = running ? s_be[11:8]    : 4'hF;

    assign sb3_we    = running ? (s_en[3] & s_we[3]) : (host_smem & host_gwe & (host_bank == 2'd3));
    assign sb3_addr  = running ? s_addr[31:24] : host_saddr;
    assign sb3_wdata = running ? s_wdata[127:96] : host_wdata;
    assign sb3_be    = running ? s_be[15:12]   : 4'hF;

    // Instruction memory write port
    assign imem_we    = running ? 1'b0 : (host_imem & host_gwe);
    assign imem_waddr = host_addr[10:2];
    assign imem_wdata = host_wdata;

    // Read data packing
    assign g_rdata = {gb3_rdata, gb2_rdata, gb1_rdata, gb0_rdata};
    assign s_rdata = {sb3_rdata, sb2_rdata, sb1_rdata, sb0_rdata};

endmodule
