module tex_filter (
    input  wire        gfx,
    input  wire  [2:0] gfx_op,
    input  wire [127:0] a,
    input  wire [127:0] b,
    input  wire  [2:0] tex_mode,
    input  wire [15:0] t00,
    input  wire [15:0] t01,
    input  wire [15:0] t02,
    input  wire [15:0] t03,
    input  wire [15:0] t10,
    input  wire [15:0] t11,
    input  wire [15:0] t12,
    input  wire [15:0] t13,
    input  wire [15:0] t20,
    input  wire [15:0] t21,
    input  wire [15:0] t22,
    input  wire [15:0] t23,
    input  wire [15:0] t30,
    input  wire [15:0] t31,
    input  wire [15:0] t32,
    input  wire [15:0] t33,
    output wire [127:0] tex_y
);
    genvar l;
    generate
        for (l = 0; l < 4; l = l + 1) begin : g_lane
            wire [31:0] u = a[32*l +: 32];
            wire [31:0] v = b[32*l +: 32];

            wire [7:0] iu = u[15:8];
            wire [7:0] iv = v[15:8];
            wire [7:0] fu = u[7:0];
            wire [7:0] fv = v[7:0];

            // wrap
            wire [8:0] iu_p1 = {1'b0, iu} + 9'd1;
            wire [8:0] iv_p1 = {1'b0, iv} + 9'd1;

            wire [4:0] x0 = tex_mode[1] ? ((iu > 8'd31) ? 5'd31 : iu[4:0])
                                        : iu[4:0];
            wire [4:0] x1 = tex_mode[1] ? ((iu_p1 > 9'd31) ? 5'd31 : iu_p1[4:0])
                                        : iu_p1[4:0];
            wire [4:0] y0 = tex_mode[2] ? ((iv > 8'd31) ? 5'd31 : iv[4:0])
                                        : iv[4:0];
            wire [4:0] y1 = tex_mode[2] ? ((iv_p1 > 9'd31) ? 5'd31 : iv_p1[4:0])
                                        : iv_p1[4:0];

            // texel select: k = (y mod 2)*2 + (x mod 2)
            wire [15:0] t0 = (l == 2'd0) ? ((y0[0] ? (x0[0] ? t03 : t02)
                                                   : (x0[0] ? t01 : t00))) :
                             (l == 2'd1) ? ((y0[0] ? (x0[0] ? t13 : t12)
                                                   : (x0[0] ? t11 : t10))) :
                             (l == 2'd2) ? ((y0[0] ? (x0[0] ? t23 : t22)
                                                   : (x0[0] ? t21 : t20))) :
                                           ((y0[0] ? (x0[0] ? t33 : t32)
                                                   : (x0[0] ? t31 : t30)));
            wire [15:0] t1 = (l == 2'd0) ? ((y0[0] ? (x1[0] ? t03 : t02)
                                                   : (x1[0] ? t01 : t00))) :
                             (l == 2'd1) ? ((y0[0] ? (x1[0] ? t13 : t12)
                                                   : (x1[0] ? t11 : t10))) :
                             (l == 2'd2) ? ((y0[0] ? (x1[0] ? t23 : t22)
                                                   : (x1[0] ? t21 : t20))) :
                                           ((y0[0] ? (x1[0] ? t33 : t32)
                                                   : (x1[0] ? t31 : t30)));
            wire [15:0] t2 = (l == 2'd0) ? ((y1[0] ? (x0[0] ? t03 : t02)
                                                   : (x0[0] ? t01 : t00))) :
                             (l == 2'd1) ? ((y1[0] ? (x0[0] ? t13 : t12)
                                                   : (x0[0] ? t11 : t10))) :
                             (l == 2'd2) ? ((y1[0] ? (x0[0] ? t23 : t22)
                                                   : (x0[0] ? t21 : t20))) :
                                           ((y1[0] ? (x0[0] ? t33 : t32)
                                                   : (x0[0] ? t31 : t30)));
            wire [15:0] t3 = (l == 2'd0) ? ((y1[0] ? (x1[0] ? t03 : t02)
                                                   : (x1[0] ? t01 : t00))) :
                             (l == 2'd1) ? ((y1[0] ? (x1[0] ? t13 : t12)
                                                   : (x1[0] ? t11 : t10))) :
                             (l == 2'd2) ? ((y1[0] ? (x1[0] ? t23 : t22)
                                                   : (x1[0] ? t21 : t20))) :
                                           ((y1[0] ? (x1[0] ? t33 : t32)
                                                   : (x1[0] ? t31 : t30)));

            // widen RGB565 -> RGB888: r8 = r5<<3 | r5>>2, g8 = g6<<2 | g6>>4
            function [7:0] widen5;
                input [4:0] c;
                widen5 = {c, 3'b000} | {5'b00000, c[4:2]};
            endfunction
            function [7:0] widen6;
                input [5:0] c;
                widen6 = {c, 2'b00} | {6'b000000, c[5:4]};
            endfunction

            wire [7:0] r00 = widen5(t0[15:11]);
            wire [7:0] g00 = widen6(t0[10:5]);
            wire [7:0] b00 = widen5(t0[4:0]);
            wire [7:0] r10 = widen5(t1[15:11]);
            wire [7:0] g10 = widen6(t1[10:5]);
            wire [7:0] b10 = widen5(t1[4:0]);
            wire [7:0] r01 = widen5(t2[15:11]);
            wire [7:0] g01 = widen6(t2[10:5]);
            wire [7:0] b01 = widen5(t2[4:0]);
            wire [7:0] r11 = widen5(t3[15:11]);
            wire [7:0] g11 = widen6(t3[10:5]);
            wire [7:0] b11 = widen5(t3[4:0]);

            // bilinear
            wire [17:0] wu = {10'd0, fu};
            wire [17:0] wv = {10'd0, fv};
            wire [17:0] wu_i = 18'd256 - wu;
            wire [17:0] wv_i = 18'd256 - wv;

            function [7:0] bl;
                input [7:0] c00, c10, c01, c11;
                input [17:0] wu, wv, wu_i, wv_i;
                reg [33:0] acc;
                begin
                    acc = c00 * wu_i * wv_i + c10 * wu * wv_i
                        + c01 * wu_i * wv  + c11 * wu * wv
                        + 34'd32768;
                    bl = acc[23:16];
                end
            endfunction

            wire [7:0] r_b = bl(r00, r10, r01, r11, wu, wv, wu_i, wv_i);
            wire [7:0] g_b = bl(g00, g10, g01, g11, wu, wv, wu_i, wv_i);
            wire [7:0] b_b = bl(b00, b10, b01, b11, wu, wv, wu_i, wv_i);

            wire [7:0] r_o = tex_mode[0] ? r_b : r00;
            wire [7:0] g_o = tex_mode[0] ? g_b : g00;
            wire [7:0] b_o = tex_mode[0] ? b_b : b00;

            wire tex_en = gfx && (gfx_op == 3'd4);

            assign tex_y[32*l +: 32] = tex_en ? {8'hFF, r_o, g_o, b_o} : 32'd0;
        end
    endgenerate
endmodule
