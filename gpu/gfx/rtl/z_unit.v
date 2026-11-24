module z_unit (
    input  wire         valid,
    input  wire         advance,
    input  wire         gfx,
    input  wire  [2:0]  gfx_op,
    input  wire  [3:0]  tmask,
    input  wire  [127:0] a,
    input  wire  [127:0] b,
    input  wire  [15:0] z_rdata0,
    input  wire  [15:0] z_rdata1,
    input  wire  [15:0] z_rdata2,
    input  wire  [15:0] z_rdata3,
    output wire  [14:0] z_raddr0,
    output wire  [14:0] z_raddr1,
    output wire  [14:0] z_raddr2,
    output wire  [14:0] z_raddr3,
    output wire         zw_we0,
    output wire         zw_we1,
    output wire         zw_we2,
    output wire         zw_we3,
    output wire  [14:0] zw_waddr0,
    output wire  [14:0] zw_waddr1,
    output wire  [14:0] zw_waddr2,
    output wire  [14:0] zw_waddr3,
    output wire  [15:0] zw_wdata0,
    output wire  [15:0] zw_wdata1,
    output wire  [15:0] zw_wdata2,
    output wire  [15:0] zw_wdata3,
    output wire  [127:0] z_y
);
    wire active = gfx & (gfx_op == 3'd6);

    // per-lane signals
    wire [15:0] x0 = a[15:0];    wire [15:0] y0 = a[31:16];   wire [15:0] z0 = b[15:0];
    wire [15:0] x1 = a[47:32];   wire [15:0] y1 = a[63:48];   wire [15:0] z1 = b[47:32];
    wire [15:0] x2 = a[79:64];   wire [15:0] y2 = a[95:80];   wire [15:0] z2 = b[79:64];
    wire [15:0] x3 = a[111:96];  wire [15:0] y3 = a[127:112]; wire [15:0] z3 = b[111:96];

    wire test0 = active & tmask[0] & (x0 < 16'd320) & (y0 < 16'd240);
    wire test1 = active & tmask[1] & (x1 < 16'd320) & (y1 < 16'd240);
    wire test2 = active & tmask[2] & (x2 < 16'd320) & (y2 < 16'd240);
    wire test3 = active & tmask[3] & (x3 < 16'd320) & (y3 < 16'd240);

    wire [1:0] bank0 = x0[1:0];
    wire [1:0] bank1 = x1[1:0];
    wire [1:0] bank2 = x2[1:0];
    wire [1:0] bank3 = x3[1:0];

    wire [26:0] full0 = y0[14:0] * 15'd80 + {13'd0, x0[15:2]};
    wire [26:0] full1 = y1[14:0] * 15'd80 + {13'd0, x1[15:2]};
    wire [26:0] full2 = y2[14:0] * 15'd80 + {13'd0, x2[15:2]};
    wire [26:0] full3 = y3[14:0] * 15'd80 + {13'd0, x3[15:2]};
    wire [14:0] idx0 = full0[14:0];
    wire [14:0] idx1 = full1[14:0];
    wire [14:0] idx2 = full2[14:0];
    wire [14:0] idx3 = full3[14:0];

    // winner per bank: priority lane 3 > 2 > 1 > 0
    // winner_sel[k][l]: lane l is bank k's winner
    wire [3:0] w0, w1, w2, w3; // w[k][l]
    assign w0[0] = test0 & (bank0 == 2'd0);
    assign w0[1] = test1 & (bank1 == 2'd0);
    assign w0[2] = test2 & (bank2 == 2'd0);
    assign w0[3] = test3 & (bank3 == 2'd0);
    assign w1[0] = test0 & (bank0 == 2'd1);
    assign w1[1] = test1 & (bank1 == 2'd1);
    assign w1[2] = test2 & (bank2 == 2'd1);
    assign w1[3] = test3 & (bank3 == 2'd1);
    assign w2[0] = test0 & (bank0 == 2'd2);
    assign w2[1] = test1 & (bank1 == 2'd2);
    assign w2[2] = test2 & (bank2 == 2'd2);
    assign w2[3] = test3 & (bank3 == 2'd2);
    assign w3[0] = test0 & (bank0 == 2'd3);
    assign w3[1] = test1 & (bank1 == 2'd3);
    assign w3[2] = test2 & (bank2 == 2'd3);
    assign w3[3] = test3 & (bank3 == 2'd3);

    // winner lane per bank (one-hot), priority 3,2,1,0
    wire [3:0] win0 = w0[3] ? 4'b1000 : w0[2] ? 4'b0100 : w0[1] ? 4'b0010 : w0[0] ? 4'b0001 : 4'b0000;
    wire [3:0] win1 = w1[3] ? 4'b1000 : w1[2] ? 4'b0100 : w1[1] ? 4'b0010 : w1[0] ? 4'b0001 : 4'b0000;
    wire [3:0] win2 = w2[3] ? 4'b1000 : w2[2] ? 4'b0100 : w2[1] ? 4'b0010 : w2[0] ? 4'b0001 : 4'b0000;
    wire [3:0] win3 = w3[3] ? 4'b1000 : w3[2] ? 4'b0100 : w3[1] ? 4'b0010 : w3[0] ? 4'b0001 : 4'b0000;

    wire any0 = |w0, any1 = |w1, any2 = |w2, any3 = |w3;

    // winner index / z per bank
    wire [14:0] widx0 = win0[3] ? idx3 : win0[2] ? idx2 : win0[1] ? idx1 : idx0;
    wire [14:0] widx1 = win1[3] ? idx3 : win1[2] ? idx2 : win1[1] ? idx1 : idx0;
    wire [14:0] widx2 = win2[3] ? idx3 : win2[2] ? idx2 : win2[1] ? idx1 : idx0;
    wire [14:0] widx3 = win3[3] ? idx3 : win3[2] ? idx2 : win3[1] ? idx1 : idx0;

    wire [15:0] wz0 = win0[3] ? z3 : win0[2] ? z2 : win0[1] ? z1 : z0;
    wire [15:0] wz1 = win1[3] ? z3 : win1[2] ? z2 : win1[1] ? z1 : z0;
    wire [15:0] wz2 = win2[3] ? z3 : win2[2] ? z2 : win2[1] ? z1 : z0;
    wire [15:0] wz3 = win3[3] ? z3 : win3[2] ? z2 : win3[1] ? z1 : z0;

    assign z_raddr0 = (valid & any0) ? widx0 : 15'd0;
    assign z_raddr1 = (valid & any1) ? widx1 : 15'd0;
    assign z_raddr2 = (valid & any2) ? widx2 : 15'd0;
    assign z_raddr3 = (valid & any3) ? widx3 : 15'd0;

    wire pass0 = any0 & (wz0 < z_rdata0);
    wire pass1 = any1 & (wz1 < z_rdata1);
    wire pass2 = any2 & (wz2 < z_rdata2);
    wire pass3 = any3 & (wz3 < z_rdata3);

    wire wr = valid & advance;

    assign zw_we0 = wr & pass0;
    assign zw_we1 = wr & pass1;
    assign zw_we2 = wr & pass2;
    assign zw_we3 = wr & pass3;

    assign zw_waddr0 = wr ? widx0 : 15'd0;
    assign zw_waddr1 = wr ? widx1 : 15'd0;
    assign zw_waddr2 = wr ? widx2 : 15'd0;
    assign zw_waddr3 = wr ? widx3 : 15'd0;

    assign zw_wdata0 = wr ? wz0 : 16'd0;
    assign zw_wdata1 = wr ? wz1 : 16'd0;
    assign zw_wdata2 = wr ? wz2 : 16'd0;
    assign zw_wdata3 = wr ? wz3 : 16'd0;

    // passing winner per lane
    wire p0 = (win0[0] & pass0) | (win1[0] & pass1) | (win2[0] & pass2) | (win3[0] & pass3);
    wire p1 = (win0[1] & pass0) | (win1[1] & pass1) | (win2[1] & pass2) | (win3[1] & pass3);
    wire p2 = (win0[2] & pass0) | (win1[2] & pass1) | (win2[2] & pass2) | (win3[2] & pass3);
    wire p3 = (win0[3] & pass0) | (win1[3] & pass1) | (win2[3] & pass2) | (win3[3] & pass3);

    assign z_y = {{32{p3}}, {32{p2}}, {32{p1}}, {32{p0}}};
endmodule
