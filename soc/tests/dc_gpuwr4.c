/* Data-cache loads while another hart stores into the GPU window: hart 0 fills a 4 KB array with plain stores, then reads it back 6 times and
 * checks every word; harts 1-3 only store to the GPU window of their own core (device writes, no RAM). TOHOST 1 = pass, else 2*(pass*100000+i)+3. */
#include <stdint.h>
#define R(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define A 0x80A00000u
#define TOHOST 0x80FFF000u
void main_(uint32_t h) {
    if (h == 0) {
        for (uint32_t i = 0; i < 1024; i++) R(A + 4 * i) = i * 2654435761u + 7;
        for (uint32_t p = 0; p < 6; p++)
            for (uint32_t i = 0; i < 1024; i++) if (R(A + 4 * i) != i * 2654435761u + 7) { R(0x80FFF004u) = R(A + 4 * i); R(0x80FFF008u) = i; R(TOHOST) = 2 * (p * 100000 + i) + 3; for (;;) ; }
        R(TOHOST) = 1;
    } else for (uint32_t n = 0; n < 100000; n++) R(0x30000000u + (h << 21) + 0x10000 + ((n & 63) << 2)) = n;
    for (;;) ;
}
asm(".section .text.init\n.globl _start\n_start:\n  csrr a0, mhartid\n  li sp, 0x80F00000\n  slli t0, a0, 14\n  sub sp, sp, t0\n  call main_\n1: j 1b\n");
