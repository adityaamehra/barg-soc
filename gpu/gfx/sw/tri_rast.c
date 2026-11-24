/* G2b: the scenes of tri.c drawn with the raster unit (rast, rast.edge); the same pixels, by the same triangle rule.
 *
 * Per triangle every warp computes the set-up (the same in every lane); after a barrier (all warps done with the triangle
 * before) warp 0 loads the box, the edge coefficients and the bias with gfx.cfg, and after a second barrier every warp
 * drains its own scan (rows y with y mod 4 = its warp number). The edge function of the rule in pixel units:
 * E(x, y) = A x + B y + C with A = -16 ey, B = 16 ex, C = ex (8 - ay) - ey (8 - ax) for the edge from a with direction (ex, ey). */
#include "../../sw/simt.h"

#define W 320
#define H 240
#define MAXT 32

int ntri;
unsigned clear;
int tri[MAXT][13];                 /* x0 y0 x1 y1 x2 y2 (1/16 pixel), c0 c1 c2, mode: 0 flat, 1 Gouraud (c ARGB8888),
                                      2 textured (c = v << 16 | u, 8.8 texels; mode bits 6:4 = gfx.cfg 32);
                                      mode bit 7: source-over blending (gfx.cfg 4); mode bit 8: depth test
                                      with the vertex depths z0 z1 z2 (0..16383) that follow */

/* gfx.cfg of edge i, from a with direction (ex, ey); returns its top-left bias bit */
static unsigned edge_cfg(unsigned i, int ax, int ay, int ex, int ey) {
    simt_gfx_cfg(16 + 3 * i, (unsigned)(-16 * ey));
    simt_gfx_cfg(17 + 3 * i, (unsigned)(16 * ex));
    simt_gfx_cfg(18 + 3 * i, (unsigned)(ex * (8 - ay) - ey * (8 - ax)));
    return (unsigned)((-ey > 0) | ((ey == 0) & (ex < 0))) << i;
}

static inline unsigned mulhu(unsigned a, unsigned b) { return (unsigned)(((unsigned long long)a * b) >> 32); }

void kernel(void) {
    unsigned tid = simt_tid(), wid = simt_wid(), nw = simt_nw();
    for (unsigned y = wid; y < H; y += 4)
        for (unsigned g = 0; g < W; g += 4)
            simt_pix(y << 16 | (g + tid), clear);

    for (int k = 0; k < ntri; k++) {
        const int *T = tri[k];
        int x0 = T[0], y0 = T[1], x1 = T[2], y1 = T[3], x2 = T[4], y2 = T[5];
        unsigned c0 = T[6], c1 = T[7], c2 = T[8], z0 = T[10], z1 = T[11], z2 = T[12];
        int a2 = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0);
        if (a2 == 0)
            continue;
        if (a2 < 0) {
            int t;
            unsigned tc;
            t = x1; x1 = x2; x2 = t;
            t = y1; y1 = y2; y2 = t;
            tc = c1; c1 = c2; c2 = tc;
            tc = z1; z1 = z2; z2 = tc;
            a2 = -a2;
        }
        int mnx = x0 < x1 ? (x0 < x2 ? x0 : x2) : (x1 < x2 ? x1 : x2), mxx = x0 > x1 ? (x0 > x2 ? x0 : x2) : (x1 > x2 ? x1 : x2);
        int mny = y0 < y1 ? (y0 < y2 ? y0 : y2) : (y1 < y2 ? y1 : y2), mxy = y0 > y1 ? (y0 > y2 ? y0 : y2) : (y1 > y2 ? y1 : y2);
        int xa = mnx >> 4, xb = mxx >> 4, ya = mny >> 4, yb = mxy >> 4;
        if (xa < 0) xa = 0;
        if (ya < 0) ya = 0;
        if (xb > W - 1) xb = W - 1;
        if (yb > H - 1) yb = H - 1;
        if (xa > xb || ya > yb)
            continue;
        int mode = T[9];
        int s = 0;
        while ((a2 >> s) >= 65536)
            s++;
        unsigned R = 0xFFFFFFFFu / (unsigned)(a2 >> s);
        simt_barrier(0, nw);
        if (wid == 0) {
            unsigned bias = edge_cfg(0, x1, y1, x2 - x1, y2 - y1) | edge_cfg(1, x2, y2, x0 - x2, y0 - y2) |
                            edge_cfg(2, x0, y0, x1 - x0, y1 - y0);
            simt_gfx_cfg(25, bias);
            simt_gfx_cfg(32, (unsigned)mode >> 4 & 7);
            simt_gfx_cfg(4, (unsigned)mode >> 7 & 1);
            simt_gfx_cfg(9, (unsigned)yb << 16 | (unsigned)xb);
            simt_gfx_cfg(8, (unsigned)ya << 16 | (unsigned)xa);        /* last: restarts every warp's scan */
        }
        simt_barrier(1, nw);
        if ((mode & 0x10F) == 0) {                       /* flat (blended or not): no weights */
            for (unsigned p = simt_rast(); p != 0xFFFFFFFFu; p = simt_rast())
                simt_pix(p, c0);
            continue;
        }
        if (mode == 1) {                                 /* plain Gouraud: its own loop, so the general one's registers do not cost it */
            for (unsigned p = simt_rast(); p != 0xFFFFFFFFu; p = simt_rast()) {
                unsigned w0 = (unsigned)(simt_rast_edge(p, 0) >> s), w1 = (unsigned)(simt_rast_edge(p, 1) >> s),
                         w2 = (unsigned)(simt_rast_edge(p, 2) >> s);
                unsigned r = mulhu(w0 * (c0 >> 16 & 255) + w1 * (c1 >> 16 & 255) + w2 * (c2 >> 16 & 255), R);
                unsigned gg = mulhu(w0 * (c0 >> 8 & 255) + w1 * (c1 >> 8 & 255) + w2 * (c2 >> 8 & 255), R);
                unsigned b = mulhu(w0 * (c0 & 255) + w1 * (c1 & 255) + w2 * (c2 & 255), R);
                simt_pix(p, 0xFF000000u | (r & 255) << 16 | (gg & 255) << 8 | (b & 255));
            }
            continue;
        }
        for (unsigned p = simt_rast(); p != 0xFFFFFFFFu; p = simt_rast()) {
            unsigned colour = c0, pos = p;
            if (mode & 0x10F) {                          /* anything but flat: the weights of the rule */
                unsigned w0 = (unsigned)(simt_rast_edge(p, 0) >> s), w1 = (unsigned)(simt_rast_edge(p, 1) >> s),
                         w2 = (unsigned)(simt_rast_edge(p, 2) >> s);
                if ((mode & 15) == 2) {
                    unsigned u = mulhu(w0 * (c0 & 0xFFFF) + w1 * (c1 & 0xFFFF) + w2 * (c2 & 0xFFFF), R);
                    unsigned v = mulhu(w0 * (c0 >> 16) + w1 * (c1 >> 16) + w2 * (c2 >> 16), R);
                    colour = simt_tex(u, v);
                } else if ((mode & 15) == 1) {
                    unsigned r = mulhu(w0 * (c0 >> 16 & 255) + w1 * (c1 >> 16 & 255) + w2 * (c2 >> 16 & 255), R);
                    unsigned gg = mulhu(w0 * (c0 >> 8 & 255) + w1 * (c1 >> 8 & 255) + w2 * (c2 >> 8 & 255), R);
                    unsigned b = mulhu(w0 * (c0 & 255) + w1 * (c1 & 255) + w2 * (c2 & 255), R);
                    colour = 0xFF000000u | (r & 255) << 16 | (gg & 255) << 8 | (b & 255);
                }
                if (mode & 0x100) {                      /* depth test: a lane that fails draws off the screen */
                    unsigned m = simt_ztest(p, mulhu(w0 * z0 + w1 * z1 + w2 * z2, R));     /* ~0 or 0 */
                    __asm__("" : "+r"(m));
                    pos = (p & m) | ((0xFFFF0000u | (p & 0xFFFF)) & ~m);
                }
            }
            simt_pix(pos, colour);
        }
    }
}
