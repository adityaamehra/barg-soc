/* Misaligned loads and stores must trap (cause 4 for loads, 6 for stores, mtval = the address), in machine mode and in supervisor mode
 * with Sv32 translation on. The handler records each trap and steps over the (non-compressed) instruction.
 * Phases: 0 lw, 1 lh, 2 sw in M mode; 3 lw, 4 lh, 5 sw in S mode with paging (virtual pages and an identity megapage); 6 lw at +3 (the
 * kernel's copy_words_unaligned pattern); 7 and 8: a COMPRESSED c.lw at a misaligned address, with the instruction at a word-aligned PC
 * (7) and at a PC that is 2 mod 4 (8), in M mode.
 * Per phase p, at 0x80FF0400 + 16 p: [0] mcause [1] mtval [2] number of traps [3] the loaded value (loads).
 * TOHOST (0x80FFF000): 1 for a pass, else phase * 4 + (1 no trap, 2 wrong cause, 3 wrong address) ... times 2 + 1. */
#include <stdint.h>
#define R(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define OUT 0x80FF0400u
#define TOHOST 0x80FFF000u
#define FLAGS 0xCFu
static volatile uint32_t phase;

__attribute__((interrupt("machine"), aligned(4))) void trap(void) {
    uint32_t c, v, e, p = phase;
    __asm__ volatile("csrr %0, mcause" : "=r"(c));
    __asm__ volatile("csrr %0, mtval" : "=r"(v));
    __asm__ volatile("csrr %0, mepc" : "=r"(e));
    R(OUT + 16 * p + 0) = c; R(OUT + 16 * p + 4) = v; R(OUT + 16 * p + 8) = R(OUT + 16 * p + 8) + 1;
    uint32_t step = ((*(volatile uint16_t *)(uintptr_t)e & 3) == 3) ? 4 : 2; /* 4 for a 32-bit instruction, 2 for a compressed one */
    __asm__ volatile("csrw mepc, %0" :: "r"(e + step));
}
#define LW(dst, a) __asm__ volatile(".option push\n.option norvc\nlw %0, 0(%1)\n.option pop" : "=r"(dst) : "r"(a) : "memory")
#define LH(dst, a) __asm__ volatile(".option push\n.option norvc\nlh %0, 0(%1)\n.option pop" : "=r"(dst) : "r"(a) : "memory")
#define SW(val, a) __asm__ volatile(".option push\n.option norvc\nsw %0, 0(%1)\n.option pop" :: "r"(val), "r"(a) : "memory")

static void run_phases(uint32_t base, uint32_t first) {
    uint32_t v;
    phase = first;     v = 0; LW(v, base + 1); R(OUT + 16 * phase + 12) = v;
    phase = first + 1; v = 0; LH(v, base + 1); R(OUT + 16 * phase + 12) = v;
    phase = first + 2; SW(0x12345678u, base + 2);
}

__attribute__((noreturn)) static void smain(void) {
    run_phases(0x40001000u, 3);            /* a virtual page, translated */
    phase = 6; { uint32_t v = 0; LW(v, 0x80400003u); R(OUT + 16 * 6 + 12) = v; }   /* identity megapage, ends in 3 */
    uint32_t code = 0;
    for (uint32_t p = 0; p < 9 && !code; p++) {
        uint32_t want = (p == 2 || p == 5) ? 6 : 4; /* stores trap with cause 6, loads with 4 */
        if (R(OUT + 16 * p + 8) != 1) code = p * 4 + 1;
        else if (R(OUT + 16 * p + 0) != want) code = p * 4 + 2;
        else if (R(OUT + 16 * p + 4) != ((p == 6 || p >= 7) ? 0x80400003u : (p < 3 ? 0x80400001u + (p == 2) : 0x40001001u + (p == 5)))) code = p * 4 + 3;
    }
    R(TOHOST) = code ? code * 2 + 1 : 1;
    for (;;) ;
}

void main(void) {
    uint32_t root = 0x80100000u, l2 = root + 0x1000u;
    __asm__ volatile("csrw mtvec, %0" :: "r"(trap));
    run_phases(0x80400000u, 0);            /* machine mode, no translation */
    { register uint32_t a5 __asm__("a5") = 0x80400003u; phase = 7;
      __asm__ volatile(".option push\n.option rvc\n.balign 4\nc.lw a4, 0(a5)\n.option pop" : : "r"(a5) : "a4", "memory");
      phase = 8;
      __asm__ volatile(".option push\n.option rvc\n.balign 4\nc.nop\nc.lw a4, 0(a5)\n.option pop" : : "r"(a5) : "a4", "memory"); }
    for (uint32_t i = 0; i < 1024; i++) { R(root + 4 * i) = 0; R(l2 + 4 * i) = 0; }
    R(root + 4 * 0x200) = (0x80000000u >> 2) | FLAGS;
    R(root + 4 * 0x201) = (0x80400000u >> 2) | FLAGS;
    R(root + 4 * 0x203) = (0x80C00000u >> 2) | FLAGS;
    R(root + 4 * (0x40001000u >> 22)) = ((l2 >> 12) << 10) | 1u;
    R(l2 + 4 * 1) = ((0x80500000u >> 12) << 10) | FLAGS; /* 0x40001000 -> 0x80500000 */
    __asm__ volatile("csrw satp, %0" :: "r"(0x80000000u | root >> 12));
    __asm__ volatile("sfence.vma");
    uint32_t ms;
    __asm__ volatile("csrr %0, mstatus" : "=r"(ms));
    ms = (ms & ~0x1800u) | 0x0800u;
    __asm__ volatile("csrw mstatus, %0" :: "r"(ms));
    __asm__ volatile("csrw mepc, %0" :: "r"(smain));
    __asm__ volatile("mret");
    for (;;) ;
}
