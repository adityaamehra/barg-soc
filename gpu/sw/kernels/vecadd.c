/* c[i] = a[i] + b[i]: a grid-stride loop, the CUDA idiom; n need not be a multiple of the thread count. */
#include "../simt.h"

#define MAX 200
int n;
int a[MAX], b[MAX], c[MAX];

void kernel(void) {
    unsigned stride = simt_nthreads();
    volatile unsigned i = simt_gtid();                     /* written in a divergent body: volatile (simt.h) */
    SIMT_WHILE(i < (unsigned)n, { c[i] = a[i] + b[i]; i = i + stride; });
}
