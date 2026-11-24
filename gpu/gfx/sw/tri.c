/* G2a: clear the screen, then draw flat and Gouraud triangles in software, by the triangle rule of docs/gfx-architecture.md.
 *
 * Warp w owns the rows y with y mod 4 = w and lane l the pixels x with x mod 4 = l, for the clear and for every triangle, so one
 * thread writes a pixel in program order and no barrier is needed. Every loop and branch depends only on the triangle, the same
 * in all lanes: a pixel outside the triangle is sent to row 0xFFFF, which `pix` drops, so there is no divergence. */
#include "../../sw/simt.h"

#define W 320
#define H 240
#define MAXT 32

int ntri;
unsigned clear;
int tri[MAXT][13];                 /* x0 y0 x1 y1 x2 y2 (1/16 pixel), c0 c1 c2 (ARGB8888), mode (0 flat, 1 Gouraud), z0 z1 z2 (unused) */

static inline unsigned mulhu(unsigned a, unsigned b) { return (unsigned)(((unsigned long long)a * b) >> 32); }

void kernel(void) {
    unsigned tid = simt_tid(), wid = simt_wid();
    for (unsigned y = wid; y < H; y += 4)
        for (unsigned g = 0; g < W; g += 4)
            simt_pix(y << 16 | (g + tid), clear);

    for (int k = 0; k < ntri; k++) {
        const int *T = tri[k];
        int x0 = T[0], y0 = T[1], x1 = T[2], y1 = T[3], x2 = T[4], y2 = T[5];
        unsigned c0 = T[6], c1 = T[7], c2 = T[8];
        int a2 = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0);
        if (a2 == 0)
            continue;
        if (a2 < 0) {
            int t;
            unsigned tc;
            t = x1; x1 = x2; x2 = t;
            t = y1; y1 = y2; y2 = t;
            tc = c1; c1 = c2; c2 = tc;
            a2 = -a2;
        }
        /* edges: 0 v1 -> v2, 1 v2 -> v0, 2 v0 -> v1; E = (bx - ax)(py - ay) - (by - ay)(px - ax); bias t for the top-left rule */
        int ax[3] = {x1, x2, x0}, ay[3] = {y1, y2, y0}, ex[3] = {x2 - x1, x0 - x2, x1 - x0}, ey[3] = {y2 - y1, y0 - y2, y1 - y0};
        int tb[3];
        for (int i = 0; i < 3; i++)
            tb[i] = (-ey[i] > 0) | ((ey[i] == 0) & (ex[i] < 0));
        int mnx = x0 < x1 ? (x0 < x2 ? x0 : x2) : (x1 < x2 ? x1 : x2), mxx = x0 > x1 ? (x0 > x2 ? x0 : x2) : (x1 > x2 ? x1 : x2);
        int mny = y0 < y1 ? (y0 < y2 ? y0 : y2) : (y1 < y2 ? y1 : y2), mxy = y0 > y1 ? (y0 > y2 ? y0 : y2) : (y1 > y2 ? y1 : y2);
        int xa = mnx >> 4, xb = mxx >> 4, ya = mny >> 4, yb = mxy >> 4;
        if (xa < 0) xa = 0;
        if (ya < 0) ya = 0;
        if (xb > W - 1) xb = W - 1;
        if (yb > H - 1) yb = H - 1;
        xa &= ~3;
        int mode = T[9];
        int s = 0;
        while ((a2 >> s) >= 65536)
            s++;
        unsigned R = 0xFFFFFFFFu / (unsigned)(a2 >> s);
        unsigned ch[3][3];
        for (int i = 0; i < 3; i++) {
            unsigned c = i == 0 ? c0 : i == 1 ? c1 : c2;
            ch[i][0] = c >> 16 & 255; ch[i][1] = c >> 8 & 255; ch[i][2] = c & 255;
        }
        for (int y = ya + (int)((wid - (unsigned)ya) & 3); y <= yb; y += 4) {
            int py = 16 * y + 8;
            for (int g = xa; g <= xb; g += 4) {
                int x = g + (int)tid, px = 16 * x + 8;
                int e0 = ex[0] * (py - ay[0]) - ey[0] * (px - ax[0]);
                int e1 = ex[1] * (py - ay[1]) - ey[1] * (px - ax[1]);
                int e2 = ex[2] * (py - ay[2]) - ey[2] * (px - ax[2]);
                unsigned in = (unsigned)((e0 + tb[0] > 0) & (e1 + tb[1] > 0) & (e2 + tb[2] > 0));
                unsigned m = 0u - in;
                __asm__("" : "+r"(m));     /* hide that m is 0 or ~0: GCC would select the position with a per-lane branch */
                unsigned colour = c0;
                if (mode) {
                    unsigned w0 = (unsigned)(e0 >> s), w1 = (unsigned)(e1 >> s), w2 = (unsigned)(e2 >> s);
                    unsigned r = mulhu(w0 * ch[0][0] + w1 * ch[1][0] + w2 * ch[2][0], R);
                    unsigned gg = mulhu(w0 * ch[0][1] + w1 * ch[1][1] + w2 * ch[2][1], R);
                    unsigned b = mulhu(w0 * ch[0][2] + w1 * ch[1][2] + w2 * ch[2][2], R);
                    colour = 0xFF000000u | (r & 255) << 16 | (gg & 255) << 8 | (b & 255);
                }
                simt_pix((((unsigned)y << 16 | (unsigned)x) & m) | (0xFFFF0000u & ~m), colour);
            }
        }
    }
}
