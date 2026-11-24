/* C = A x B for N x N signed 8-bit matrices with 32-bit results, on the tensor unit: each warp computes 4 x 4 output
 * tiles, accumulating N/4 mma.i8 steps per tile in the warp's accumulator (as a CUDA WMMA kernel accumulates over k). A is row-major; B is given
 * transposed (bt[j][k] = B[k][j]) so that each thread loads its column of B as one 32-bit word. */
#include "../simt.h"

#define N 16
signed char a[N][N] __attribute__((aligned(4)));
signed char bt[N][N] __attribute__((aligned(4)));
int c[N][N];

void kernel(void) {
    unsigned lane = simt_tid(), warp = simt_wid(), warps = simt_nw();
    for (unsigned tile = warp; tile < (N / 4) * (N / 4); tile += warps) {      /* uniform within the warp */
        unsigned ti = tile / (N / 4) * 4, tj = tile % (N / 4) * 4;
        simt_mma_zero();
        for (unsigned k = 0; k < N; k += 4) {
            unsigned a_row = *(const unsigned *)&a[ti + lane][k];      /* row ti+lane of A, elements k..k+3 */
            unsigned b_col = *(const unsigned *)&bt[tj + lane][k];     /* column tj+lane of B, elements k..k+3 */
            simt_mma_i8(a_row, b_col);
        }
        for (unsigned j = 0; j < 4; j++) c[ti + lane][tj + j] = simt_mma_ld(j);
    }
}
