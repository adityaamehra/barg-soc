/* Collatz steps of start[i]: a loop with a data-dependent trip count and a data-dependent if/else inside it, the case that
 * makes SIMT divergence handling necessary. The variables written in divergent bodies are volatile (simt.h, the one rule). */
#include "../simt.h"

#define MAX 64
int n;
unsigned start[MAX];
unsigned steps[MAX];

void kernel(void) {
    unsigned stride = simt_nthreads();
    volatile unsigned i = simt_gtid();
    SIMT_WHILE(i < (unsigned)n, {
        volatile unsigned v = start[i], s = 0;
        SIMT_WHILE(v != 1, {
            SIMT_IF(v & 1) { v = 3 * v + 1; } SIMT_ELSE { v = v >> 1; } SIMT_ENDIF;
            s = s + 1;
        });
        steps[i] = s;
        i = i + stride;
    });
}
