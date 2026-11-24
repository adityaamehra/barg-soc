module mip_merge_s (
    input  wire [11:0] mip_sw,
    input  wire        meip,
    input  wire        mtip,
    input  wire        msip,
    input  wire        seip,
    output wire [11:0] mip
);

    assign mip[0]  = 1'b0;
    assign mip[1]  = mip_sw[1];
    assign mip[2]  = 1'b0;
    assign mip[3]  = msip;
    assign mip[4]  = 1'b0;
    assign mip[5]  = mip_sw[5];
    assign mip[6]  = 1'b0;
    assign mip[7]  = mtip;
    assign mip[8]  = 1'b0;
    assign mip[9]  = mip_sw[9] | seip;
    assign mip[10] = 1'b0;
    assign mip[11] = meip;

endmodule
