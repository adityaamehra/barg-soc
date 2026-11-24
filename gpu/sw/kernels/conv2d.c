/* A 3 x 3 convolution (valid padding) of an H x W integer image: one output pixel per thread in a grid-stride loop. */
#include "../simt.h"

#define H 12
#define W 12
int img[H][W];
int k[3][3];
int out[H - 2][W - 2];

void kernel(void) {
    unsigned stride = simt_nthreads();
    volatile unsigned p = simt_gtid();                      /* written in a divergent body: volatile (simt.h) */
    SIMT_WHILE(p < (unsigned)((H - 2) * (W - 2)), {
        unsigned y = p / (W - 2), x = p % (W - 2);
        int s = 0;
        for (int dy = 0; dy < 3; dy++)
            for (int dx = 0; dx < 3; dx++)
                s += img[y + dy][x + dx] * k[dy][dx];
        out[y][x] = s;
        p = p + stride;
    });
}
