module tex_host (
    input host_en,
    input host_we,
    input [31:0] host_addr,
    input [31:0] host_wdata,
    output t_we0,
    output t_we1,
    output t_we2,
    output t_we3,
    output [7:0] t_waddr,
    output [15:0] t_wdata_lo,
    output [15:0] t_wdata_hi
);

    wire hit = host_en & host_we &
               (host_addr >= 32'h5000_0000) &
               (host_addr <  32'h5000_0800);

    assign t_we0 = hit & ~host_addr[6];
    assign t_we1 = hit & ~host_addr[6];
    assign t_we2 = hit &  host_addr[6];
    assign t_we3 = hit &  host_addr[6];

    assign t_waddr = {host_addr[10:7], host_addr[5:2]};
    assign t_wdata_lo = host_wdata[15:0];
    assign t_wdata_hi = host_wdata[31:16];

endmodule
