/* The sum of an array, the way a CUDA reduction is written: per-thread partial sums, a butterfly within each warp (shuffle),
 * one value per warp in shared memory, a barrier, and warp 0 adds the warp totals. */
#include "../simt.h"

#define MAX 256
int n;
int x[MAX];
int total;
SIMT_SHARED int warp_sum[4];

void kernel(void) {
    unsigned stride = simt_nthreads();
    volatile unsigned i = simt_gtid();                     /* written in a divergent body: volatile (simt.h) */
    volatile int acc = 0;
    SIMT_WHILE(i < (unsigned)n, { acc = acc + x[i]; i = i + stride; });
    int sum = acc;
    for (int m = 1; m < (int)simt_nt(); m <<= 1)
        sum += simt_shfl_xor(sum, m);
    SIMT_IF(simt_tid() == 0) { warp_sum[simt_wid()] = sum; } SIMT_ENDIF;
    simt_barrier(0, simt_nw());
    SIMT_IF(simt_gtid() == 0) {
        int t = 0;
        for (unsigned w = 0; w < simt_nw(); w++) t += warp_sum[w];
        total = t;
    } SIMT_ENDIF;
}
