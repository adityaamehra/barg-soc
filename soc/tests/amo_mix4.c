/* Four harts update one counter at the same time: harts 0 and 1 with amoadd.w, harts 2 and 3 with an lr.w/sc.w retry loop. No update may be lost:
 * the counter must end at 4 * N. TOHOST: 1 = pass, else the counter's final value * 2 + 1 (so a lost update shows as a smaller number). */
#include <stdint.h>
#define R(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define C 0x80FF0800u
#define DONE 0x80FF0840u
#define TOHOST 0x80FFF000u
#define N 3000
void main_(uint32_t h) {
    uint32_t c = C;
    if (h < 2) for (int i = 0; i < N; i++) __asm__ volatile("amoadd.w x0, %0, (%1)" :: "r"(1), "r"(c) : "memory");
    else for (int i = 0; i < N; i++) { uint32_t t, r; do { __asm__ volatile("lr.w %0, (%2)\n addi %0, %0, 1\n sc.w %1, %0, (%2)" : "=&r"(t), "=&r"(r) : "r"(c) : "memory"); } while (r); }
    __asm__ volatile("amoadd.w x0, %0, (%1)" :: "r"(1), "r"((uint32_t)DONE) : "memory");
    if (h == 0) { while (R(DONE) != 4) ; uint32_t v = R(C); R(TOHOST) = v == 4 * N ? 1 : v * 2 + 1; }
    for (;;) ;
}
asm(".section .text.init\n.globl _start\n_start:\n  csrr a0, mhartid\n  li sp, 0x80F00000\n  slli t0, a0, 14\n  sub sp, sp, t0\n  call main_\n1: j 1b\n");
