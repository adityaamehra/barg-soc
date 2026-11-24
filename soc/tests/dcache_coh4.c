/* Cache coherence of the four data caches: in round r hart (r mod 4) writes a 64-word array with plain stores (value r*1000+i), then raises a flag
 * with an atomic swap; the other three harts wait for the flag with plain loads, then read the whole array (through their own caches, which hold
 * last round's values) and check every word. A counter of finished readers lets the writer go on. TOHOST: 1 = pass, else 2*(round*16+hart)+1... of the first error. */
#include <stdint.h>
#define R(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define ARR 0x80F20000u
#define FLAG 0x80F20400u
#define CNT 0x80F20440u
#define BAD 0x80F20480u
#define TOHOST 0x80FFF000u
#define ROUNDS 48
static inline void swap(uint32_t a, uint32_t v) { uint32_t o; __asm__ volatile("amoswap.w %0, %1, (%2)" : "=r"(o) : "r"(v), "r"(a) : "memory"); }
static inline void add(uint32_t a, uint32_t v) { __asm__ volatile("amoadd.w x0, %0, (%1)" :: "r"(v), "r"(a) : "memory"); }
void main_(uint32_t h) {
    for (uint32_t r = 0; r < ROUNDS; r++) {
        if (h == (r & 3)) {
            while (R(CNT) != 3 * r) ;                              /* the readers of the last round are done */
            for (uint32_t i = 0; i < 64; i++) R(ARR + 4 * i) = r * 1000 + i;
            swap(FLAG, r + 1);
        } else {
            while (R(FLAG) != r + 1) ;
            for (uint32_t i = 0; i < 64; i++) if (R(ARR + 4 * i) != r * 1000 + i) { add(BAD, 1); R(TOHOST) = 2 * (r * 16 + h) + 3; for (;;) ; }
            add(CNT, 1);
        }
    }
    if (h == 0) { while (R(CNT) != 3 * ROUNDS - 0) if (R(BAD)) break; R(TOHOST) = R(BAD) ? 7 : 1; }
    for (;;) ;
}
asm(".section .text.init\n.globl _start\n_start:\n  csrr a0, mhartid\n  li sp, 0x80F00000\n  slli t0, a0, 14\n  sub sp, sp, t0\n  call main_\n1: j 1b\n");
