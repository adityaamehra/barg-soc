/* Four harts, each with its own Sv32 page table, run in supervisor mode and thrash their 8-entry TLBs at the same time.
 *
 * Per hart h (all start at 0x80000000; the harts do not share any table or data page):
 *   root table at 0x80100000 + 0x2000 h, second-level table 4 KB above it.
 *   identity megapages (RWX, A, D) for 0x80000000..0x807FFFFF and 0x80C00000..0x80FFFFFF (code, tables, stacks, the done counter).
 *   virtual 0x40000000 + 0x1000 i (i = 0..31) -> physical frame 0x80400000 + 0x1000 (32 h + i) (4 KB pages).
 * In S mode, 4 rounds: write (h << 24 | round << 16 | page << 8 | k) at word k of pages visited in a scrambled order, which evicts
 * entries constantly, then read every word back through the virtual address and through the identity-mapped physical frame.
 * A failure is recorded at 0x80FF0010 + 4 h (the round, page and which check in the code); a hart then adds 1 to 0x80FF0000. Hart 0
 * waits for all four, then writes TOHOST (0x80FFF000): 1 for a pass, else the first nonzero failure code * 2 + 1. */
#include <stdint.h>
#define R(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define DONE 0x80FF0000u
#define FAILW 0x80FF0010u
#define TOHOST 0x80FFF000u
#define VA 0x40000000u
#define PAGES 32
#define ROUNDS 4
#define FLAGS 0xCFu /* V R W X A D */
#ifndef NH
#define NH 4 /* harts that run the test (the runner passes 1 for --solo) */
#endif

static inline uint32_t hartid(void) { uint32_t h; __asm__ volatile("csrr %0, mhartid" : "=r"(h)); return h; }
/* mhartid is a machine CSR: supervisor code gets its hart number from sscratch, which machine code sets before the mret */
static inline uint32_t shart(void) { uint32_t h; __asm__ volatile("csrr %0, sscratch" : "=r"(h)); return h; }

#define STAGE(h, n) R(0x80FF0200u + 4 * (h)) = (n) /* progress marker, for diagnosis */
__attribute__((noreturn)) static void smain(void) {
    uint32_t h = shart(), code = 0;
    STAGE(h, 3);
    for (uint32_t r = 0; r < ROUNDS && !code; r++) {
        for (uint32_t n = 0; n < PAGES; n++) {
            uint32_t i = (n * 5 + r * 3) % PAGES; /* a scrambled visit order that changes every round */
            for (uint32_t k = 0; k < 4; k++) R(VA + 0x1000 * i + 4 * k) = h << 24 | r << 16 | i << 8 | k;
        }
        for (uint32_t n = 0; n < PAGES && !code; n++) {
            uint32_t i = (n * 7 + r) % PAGES;
            uint32_t phys = 0x80400000u + 0x1000u * (32 * h + i);
            for (uint32_t k = 0; k < 4 && !code; k++) {
                uint32_t want = h << 24 | r << 16 | i << 8 | k;
                if (R(VA + 0x1000 * i + 4 * k) != want) code = 1 + (r << 12 | i << 4 | 0);
                else if (R(phys + 4 * k) != want) code = 1 + (r << 12 | i << 4 | 1);
            }
        }
    }
    STAGE(h, 4);
    R(FAILW + 4 * h) = code;
    __atomic_fetch_add((volatile uint32_t *)DONE, 1u, __ATOMIC_RELEASE);
    if (h == 0) {
        while (R(DONE) != NH) ;
        for (uint32_t k = 0; k < NH; k++) if (R(FAILW + 4 * k)) { R(TOHOST) = (k * 100000 + R(FAILW + 4 * k)) * 2 + 1; for (;;) ; }
        R(TOHOST) = 1;
    }
    for (;;) ;
}

/* a trap nobody expected: record cause, pc and value at 0x80FF0100 + 16 h and finish with a failure code */
__attribute__((interrupt("machine"), aligned(4))) void trap(void) {
    uint32_t c, e, v, h = hartid();
    __asm__ volatile("csrr %0, mcause" : "=r"(c));
    __asm__ volatile("csrr %0, mepc" : "=r"(e));
    __asm__ volatile("csrr %0, mtval" : "=r"(v));
    R(0x80FF0100u + 16 * h) = c; R(0x80FF0104u + 16 * h) = e; R(0x80FF0108u + 16 * h) = v;
    R(TOHOST) = (0x7000000u + h) * 2 + 1;
    for (;;) ;
}

void main(void) {
    uint32_t h = hartid();
    STAGE(h, 1);
    uint32_t root = 0x80100000u + 0x2000u * h, l2 = root + 0x1000u;
    for (uint32_t i = 0; i < 1024; i++) { R(root + 4 * i) = 0; R(l2 + 4 * i) = 0; }
    R(root + 4 * 0x200) = (0x80000000u >> 2) | FLAGS;
    R(root + 4 * 0x201) = (0x80400000u >> 2) | FLAGS;
    R(root + 4 * 0x203) = (0x80C00000u >> 2) | FLAGS;
    R(root + 4 * (VA >> 22)) = ((l2 >> 12) << 10) | 1u;
    for (uint32_t i = 0; i < PAGES; i++) R(l2 + 4 * i) = (((0x80400000u + 0x1000u * (32 * h + i)) >> 12) << 10) | FLAGS;
    STAGE(h, 2);
#ifndef BARE /* -DBARE: drop to supervisor mode with translation off (for bisecting) */
    __asm__ volatile("csrw satp, %0" :: "r"(0x80000000u | root >> 12));
    __asm__ volatile("sfence.vma");
#endif
    uint32_t ms;
    __asm__ volatile("csrr %0, mstatus" : "=r"(ms));
    ms = (ms & ~0x1800u) | 0x0800u; /* MPP = supervisor */
    __asm__ volatile("csrw mstatus, %0" :: "r"(ms));
    __asm__ volatile("csrw sscratch, %0" :: "r"(h));
    __asm__ volatile("csrw mepc, %0" :: "r"(smain));
    __asm__ volatile("csrw mtvec, %0" :: "r"(trap));
    __asm__ volatile("mret");
    for (;;) ;
}
