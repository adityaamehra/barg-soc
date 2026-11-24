module z_host (
    input  wire        host_en,
    input  wire        host_we,
    input  wire [31:0] host_addr,
    input  wire [31:0] host_wdata,
    output wire        zh_we0,
    output wire        zh_we1,
    output wire        zh_we2,
    output wire        zh_we3,
    output wire [14:0] zh_waddr,
    output wire [15:0] zh_wdata_lo,
    output wire [15:0] zh_wdata_hi
);

    wire hit = host_en & host_we &
               (host_addr >= 32'h4004_0000) &
               (host_addr <  32'h4006_5800);

    assign zh_we0 = hit & ~host_addr[2];
    assign zh_we1 = hit & ~host_addr[2];
    assign zh_we2 = hit &  host_addr[2];
    assign zh_we3 = hit &  host_addr[2];

    assign zh_waddr    = host_addr[17:3];
    assign zh_wdata_lo = host_wdata[15:0];
    assign zh_wdata_hi = host_wdata[31:16];

endmodule
