/* C = A x B (16 x 16, INT8 in, INT32 out) tiled through shared memory, the way a CUDA shared-memory GEMM is written:
 * in each round every warp owns one 4 x 4 output tile; for each slice of K, every thread of the core copies part of A and of
 * B (transposed) into shared memory, a barrier, each warp runs mma.i8 on its tile from shared memory, and a second barrier
 * before the next slice overwrites it. Every warp runs the same rounds, so the barriers always see all the warps
 * (16 tiles: 1, 2 or 4 warps divide them evenly). */
#include "../simt.h"

#define N 16
#define KS 8                                   /* K slice */
#define TILES ((N / 4) * (N / 4))
signed char a[N][N] __attribute__((aligned(4)));
signed char bt[N][N] __attribute__((aligned(4)));
int c[N][N];
SIMT_SHARED unsigned sa[N][KS / 4 + 1];        /* the slice of A: row r, words of 4 int8; +1 pads the row to an odd stride (fewer bank conflicts) */
SIMT_SHARED unsigned sb[N][KS / 4 + 1];        /* the slice of B transposed: column c; padded the same way */

void kernel(void) {
    unsigned lane = simt_tid(), warp = simt_wid(), warps = simt_nw();
    unsigned t = simt_gtid(), threads = simt_nthreads();
    for (unsigned round = 0; round < TILES / warps; round++) {
        unsigned tile = warp + round * warps;
        unsigned ti = tile / (N / 4) * 4, tj = tile % (N / 4) * 4;
        simt_mma_zero();
        for (unsigned k0 = 0; k0 < N; k0 += KS) {
            for (unsigned w = t; w < N * (KS / 4); w += threads) {   /* 32 words; uniform when threads divides 32 */
                unsigned r = w / (KS / 4), col = w % (KS / 4);
                sa[r][col] = *(const unsigned *)&a[r][k0 + 4 * col];
                sb[r][col] = *(const unsigned *)&bt[r][k0 + 4 * col];
            }
            simt_barrier(0, warps);
            for (unsigned kk = 0; kk < KS / 4; kk++)
                simt_mma_i8(sa[ti + lane][kk], sb[tj + lane][kk]);
            simt_barrier(1, warps);
        }
        for (unsigned j = 0; j < 4; j++) c[ti + lane][tj + j] = simt_mma_ld(j);
    }
}
