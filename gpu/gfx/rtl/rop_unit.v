module rop_unit (
    input  wire         valid,
    input  wire         advance,
    input  wire         gfx,
    input  wire  [2:0]  gfx_op,
    input  wire  [3:0]  tmask,
    input  wire  [127:0] a,
    input  wire  [127:0] b,
    input  wire  [8:0]  sc_x0,
    input  wire  [8:0]  sc_y0,
    input  wire  [8:0]  sc_x1,
    input  wire  [8:0]  sc_y1,
    input  wire         blend,
    input  wire  [15:0] vw_rdata0,
    input  wire  [15:0] vw_rdata1,
    input  wire  [15:0] vw_rdata2,
    input  wire  [15:0] vw_rdata3,
    output wire         r_we0,
    output wire         r_we1,
    output wire         r_we2,
    output wire         r_we3,
    output wire  [14:0] r_waddr0,
    output wire  [14:0] r_waddr1,
    output wire  [14:0] r_waddr2,
    output wire  [14:0] r_waddr3,
    output wire  [15:0] r_wdata0,
    output wire  [15:0] r_wdata1,
    output wire  [15:0] r_wdata2,
    output wire  [15:0] r_wdata3,
    output wire  [14:0] r_raddr0,
    output wire  [14:0] r_raddr1,
    output wire  [14:0] r_raddr2,
    output wire  [14:0] r_raddr3
);

    wire act = valid & advance & gfx & (gfx_op == 3'd5);
    wire pre = valid & gfx & (gfx_op == 3'd5);

    // blend helper: (s*a + d*(255-a)) / 255 rounded
    function [7:0] blend_ch;
        input [7:0] s;
        input [7:0] d;
        input [7:0] aa;
        reg [15:0] xv;
        reg [15:0] xb;
        begin
            xv = s * aa + d * (8'd255 - aa);
            xb = xv + 16'd128;
            blend_ch = (xb + (xb >> 8)) >> 8;
        end
    endfunction

    // per-lane signals
    wire [15:0] lx  [0:3];
    wire [15:0] ly  [0:3];
    wire [31:0] col [0:3];
    wire        en  [0:3];
    wire        draww [0:3];
    wire        drawp [0:3];
    wire [1:0]  bk  [0:3];
    wire [14:0] ix  [0:3];
    wire [15:0] wd  [0:3];

    genvar g;
    generate
        for (g = 0; g < 4; g = g + 1) begin : LANE
            wire [31:0] pos = a[g*32 +: 32];
            assign lx[g]  = pos[15:0];
            assign ly[g]  = pos[31:16];
            assign col[g] = b[g*32 +: 32];

            wire [15:0] sx0 = {7'd0, sc_x0};
            wire [15:0] sx1 = {7'd0, sc_x1};
            wire [15:0] sy0 = {7'd0, sc_y0};
            wire [15:0] sy1 = {7'd0, sc_y1};

            wire inb  = (lx[g] < 16'd320) & (ly[g] < 16'd240);
            wire insc = (sx0 <= lx[g]) & (lx[g] < sx1) &
                        (sy0 <= ly[g]) & (ly[g] < sy1);

            assign en[g]    = tmask[g] & inb & insc;
            assign draww[g] = en[g] & act;
            assign drawp[g] = en[g] & pre;

            assign bk[g] = lx[g][1:0];

            wire [15:0] ymul = {8'd0, ly[g][7:0]} * 8'd80;
            assign ix[g] = ymul[14:0] + {8'd0, lx[g][8:2]};

            wire [15:0] d = (bk[g] == 2'd0) ? vw_rdata0 :
                            (bk[g] == 2'd1) ? vw_rdata1 :
                            (bk[g] == 2'd2) ? vw_rdata2 :
                                              vw_rdata3;

            wire [7:0] sa = col[g][31:24];
            wire [7:0] sr = col[g][23:16];
            wire [7:0] sg = col[g][15:8];
            wire [7:0] sb = col[g][7:0];

            wire [7:0] dr = {d[15:11], d[15:13]};
            wire [7:0] dg = {d[10:5],  d[10:9]};
            wire [7:0] db = {d[4:0],   d[4:2]};

            wire [7:0] fr = blend ? blend_ch(sr, dr, sa) : sr;
            wire [7:0] fg = blend ? blend_ch(sg, dg, sa) : sg;
            wire [7:0] fb = blend ? blend_ch(sb, db, sa) : sb;

            assign wd[g] = {fr[7:3], fg[7:2], fb[7:3]};
        end
    endgenerate

    // per-bank winner selection (highest-numbered lane wins)
    wire [3:0]  we_w;
    wire [14:0] wa_w [0:3];
    wire [15:0] wdo_w [0:3];
    wire [14:0] ra_w [0:3];

    genvar k;
    generate
        for (k = 0; k < 4; k = k + 1) begin : BANK
            wire [1:0] kk = k[1:0];
            wire h0w = draww[0] & (bk[0] == kk);
            wire h1w = draww[1] & (bk[1] == kk);
            wire h2w = draww[2] & (bk[2] == kk);
            wire h3w = draww[3] & (bk[3] == kk);
            wire [3:0] hitw = {h3w, h2w, h1w, h0w};

            assign we_w[k] = |hitw;
            assign wa_w[k] = hitw[3] ? ix[3] :
                             hitw[2] ? ix[2] :
                             hitw[1] ? ix[1] :
                             hitw[0] ? ix[0] : 15'd0;
            assign wdo_w[k] = hitw[3] ? wd[3] :
                              hitw[2] ? wd[2] :
                              hitw[1] ? wd[1] :
                              hitw[0] ? wd[0] : 16'd0;

            wire h0r = drawp[0] & (bk[0] == kk);
            wire h1r = drawp[1] & (bk[1] == kk);
            wire h2r = drawp[2] & (bk[2] == kk);
            wire h3r = drawp[3] & (bk[3] == kk);
            wire [3:0] hitr = {h3r, h2r, h1r, h0r};

            assign ra_w[k] = hitr[3] ? ix[3] :
                             hitr[2] ? ix[2] :
                             hitr[1] ? ix[1] :
                             hitr[0] ? ix[0] : 15'd0;
        end
    endgenerate

    assign r_we0    = we_w[0];
    assign r_we1    = we_w[1];
    assign r_we2    = we_w[2];
    assign r_we3    = we_w[3];
    assign r_waddr0 = wa_w[0];
    assign r_waddr1 = wa_w[1];
    assign r_waddr2 = wa_w[2];
    assign r_waddr3 = wa_w[3];
    assign r_wdata0 = wdo_w[0];
    assign r_wdata1 = wdo_w[1];
    assign r_wdata2 = wdo_w[2];
    assign r_wdata3 = wdo_w[3];
    assign r_raddr0 = ra_w[0];
    assign r_raddr1 = ra_w[1];
    assign r_raddr2 = ra_w[2];
    assign r_raddr3 = ra_w[3];

endmodule
