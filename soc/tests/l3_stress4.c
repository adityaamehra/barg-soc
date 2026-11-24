/* The cache hierarchy under capacity pressure: a 160 KB region (more than the 128 KB last-level cache, five times an L2), written by four harts
 * with interleaved words (every line is shared), read back in full by every hart, then updated by contended atomic adds. Dirty lines are evicted
 * and written back on the way; every word read must be the last one written. TOHOST: 1 = pass, else 2*(phase*100000+index)+3... of the first error. */
#include <stdint.h>
#define R(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define BASE 0x80A00000u
#define NW 40960u
#define CNT 0x80F20440u
#define TOHOST 0x80FFF000u
static inline void add(uint32_t a, uint32_t v) { __asm__ volatile("amoadd.w x0, %0, (%1)" :: "r"(v), "r"(a) : "memory"); }
static inline uint32_t val(uint32_t i) { return (i * 2654435761u) ^ 0x1234u; }
static void barrier(uint32_t n) { add(CNT, 1); while (R(CNT) != 4 * n) ; }
void main_(uint32_t h) {
    for (uint32_t i = h; i < NW; i += 4) R(BASE + 4 * i) = val(i);
    barrier(1);
    for (uint32_t i = 0; i < NW; i++) if (R(BASE + 4 * i) != val(i)) { R(TOHOST) = 2 * (1 * 100000 + i) + 3; for (;;) ; }
    barrier(2);
    for (uint32_t i = 0; i < NW; i += 16) add(BASE + 4 * i, 1);
    barrier(3);
    for (uint32_t i = 0; i < NW; i++) {
        uint32_t want = val(i) + ((i & 15) == 0 ? 4 : 0);
        if (R(BASE + 4 * i) != want) { R(TOHOST) = 2 * (3 * 100000 + i) + 3; for (;;) ; }
    }
    barrier(4);
    if (h == 0) R(TOHOST) = 1;
    for (;;) ;
}
asm(".section .text.init\n.globl _start\n_start:\n  csrr a0, mhartid\n  li sp, 0x80F00000\n  slli t0, a0, 14\n  sub sp, sp, t0\n  call main_\n1: j 1b\n");
