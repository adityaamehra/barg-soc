/* Posted stores: the core goes on as soon as the memory engine has taken a plain store. Each hart does 30000 random byte, half-word and word stores into its own
 * 256-word region (plain stores, read back with plain loads in the next instructions, so the data cache and the in-flight write must agree), and the same update to a
 * shadow region through atomics (uncached, ordered after every earlier store of the hart). After every store the word is compared with the shadow; at the end
 * every word. Four harts at once, so the engine is shared. TOHOST: 1 = pass, else 2*(hart*100000+step)+3 of the first mismatch. */
#include <stdint.h>
#define R(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define B(a) (*(volatile uint8_t *)(uintptr_t)(a))
#define H(a) (*(volatile uint16_t *)(uintptr_t)(a))
#define A_BASE 0x80B00000u
#define S_BASE 0x80B10000u
#define TOHOST 0x80FFF000u
#define CNT 0x80F20440u
static inline uint32_t amo_read(uint32_t a) { uint32_t o; __asm__ volatile("amoadd.w %0, x0, (%1)" : "=r"(o) : "r"(a) : "memory"); return o; }
static inline void amo_write(uint32_t a, uint32_t v) { uint32_t o; __asm__ volatile("amoswap.w %0, %1, (%2)" : "=r"(o) : "r"(v), "r"(a) : "memory"); }
static inline void add(uint32_t a, uint32_t v) { __asm__ volatile("amoadd.w x0, %0, (%1)" :: "r"(v), "r"(a) : "memory"); }
void main_(uint32_t h) {
    uint32_t a = A_BASE + h * 0x1000, s = S_BASE + h * 0x1000, x = 12345u + h * 777u;
    for (uint32_t i = 0; i < 256; i++) { R(a + 4 * i) = 0; amo_write(s + 4 * i, 0); }
    for (uint32_t n = 0; n < 30000; n++) {
        x = x * 1664525u + 1013904223u;
        uint32_t idx = (x >> 8) & 255, kind = (x >> 20) % 3, byte = (x >> 4) & 3, v = x * 2654435761u;
        uint32_t w = amo_read(s + 4 * idx);
        if (kind == 0) { B(a + 4 * idx + byte) = (uint8_t)v; w = (w & ~(0xFFu << (8 * byte))) | ((v & 0xFFu) << (8 * byte)); }
        else if (kind == 1) { H(a + 4 * idx + (byte & 2)) = (uint16_t)v; uint32_t sh = 8 * (byte & 2); w = (w & ~(0xFFFFu << sh)) | ((v & 0xFFFFu) << sh); }
        else { R(a + 4 * idx) = v; w = v; }
        amo_write(s + 4 * idx, w);
        if (R(a + 4 * idx) != w) { R(TOHOST) = 2 * (h * 100000 + n) + 3; for (;;) ; }
    }
    for (uint32_t i = 0; i < 256; i++) if (R(a + 4 * i) != amo_read(s + 4 * i)) { R(TOHOST) = 2 * (h * 100000 + 99999) + 3; for (;;) ; }
    add(CNT, 1);
    if (h == 0) { while (R(CNT) != 4) ; R(TOHOST) = 1; }
    for (;;) ;
}
asm(".section .text.init\n.globl _start\n_start:\n  csrr a0, mhartid\n  li sp, 0x80F00000\n  slli t0, a0, 14\n  sub sp, sp, t0\n  call main_\n1: j 1b\n");
