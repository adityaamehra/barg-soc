/* fflags/frm/fcsr and mstatus.FS through CSR instructions on the FP core: the sequence of rv32uf-move's first cases, step by step.
 * Results at 0x80FF0400 + 4 k: [k] value read at step k; the trap handler records mcause/mepc/mtval at 0x80FF0500 and skips the instruction.
 * TOHOST 1 when no trap and all values right, else step*2+1 of the first wrong one, 0x7F1 if a trap happened. */
#include <stdint.h>
#define R(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define OUT 0x80FF0400u
#define TOHOST 0x80FFF000u
__attribute__((interrupt("machine"), aligned(4))) void trap(void) {
    uint32_t c, v, e;
    __asm__ volatile("csrr %0, mcause" : "=r"(c));
    __asm__ volatile("csrr %0, mtval" : "=r"(v));
    __asm__ volatile("csrr %0, mepc" : "=r"(e));
    uint32_t n = R(OUT + 0x100);
    R(OUT + 0x104 + 12 * n) = c; R(OUT + 0x108 + 12 * n) = e; R(OUT + 0x10c + 12 * n) = v; R(OUT + 0x100) = n + 1;
    R(TOHOST) = (c << 24) | (R(OUT + 0x200) << 8) | 0x80000000u;      /* a trap ends the test: cause in bits 27:24, mepc low bits */
    for (;;) ;
}
#define X(k, ...) do { R(OUT + 0x200) = (k); uint32_t r = 0xDEAD; __asm__ volatile(".option push\n.option norvc\n" __VA_ARGS__ "\n.option pop" : "+r"(r) :: "memory", "a0", "a1"); R(OUT + 4 * (k)) = r; } while (0)
int main(void) {
    uint32_t want[] = {0, 0x1, 0x34, 0x14, 0x01, 0x54, 0x14, 0x50}, ok = 1, bad = 0;
    __asm__ volatile("csrw mtvec, %0" :: "r"(trap));
    __asm__ volatile("csrs mstatus, %0" :: "r"(1u << 13));              /* FS = initial */
    uint32_t ms; __asm__ volatile("csrr %0, mstatus" : "=r"(ms)); R(OUT + 0xF0) = ms;
    X(1, "csrwi 0x003, 1\n li a0, 0x1234\n csrrw a1, 0x003, a0\n mv %0, a1");   /* old fcsr: 1 */
    X(2, "csrrs %0, 0x003, x0");                                           /* 0x34 */
    X(3, "csrrs %0, 0x001, x0");                                           /* 0x14 */
    X(4, "csrrwi %0, 0x002, 2");                                           /* old frm: 1 */
    X(5, "csrrs %0, 0x003, x0");                                           /* 0x54 */
    X(6, "csrrci %0, 0x001, 4");                                           /* old fflags 0x14 */
    X(7, "csrrs %0, 0x003, x0");                                           /* 0x50 */
    for (int k = 1; k < 8 && ok; k++) if (R(OUT + 4 * k) != want[k]) { ok = 0; bad = k; }
    R(TOHOST) = R(OUT + 0x100) ? 0x7F1 : (ok ? 1 : bad * 2 + 1);
    for (;;) ;
}
