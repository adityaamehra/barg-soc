/* sstatus.SUM: the sequence the Linux kernel uses to reach user memory. One hart, supervisor mode, Sv32.
 * Tables: identity megapages (U = 0) for 0x80000000..0x807FFFFF and 0x80C00000..0x80FFFFFF; user page 0x40000000 (U = 1, R W, A D) ->
 * physical 0x80400000, which holds the word 0xCAFE0001.
 * In S mode: (1) sstatus has SUM = 0; (2) csrrs sets SUM, returns the old value (SUM = 0), sstatus then has SUM = 1; (3) a load from the
 * user page returns 0xCAFE0001; (4) csrrc clears SUM and returns the old value (SUM = 1); (5) the load now faults (a machine trap with
 * mcause 13, no delegation); the handler checks mcause and the faulting address and finishes.
 * Results at 0x80FF0300..: [0] sstatus (1)  [1] old (2)  [2] sstatus after set (2)  [3] user word (3)  [4] old (4)  [5] sstatus after clear
 * [6] mcause  [7] mtval.  TOHOST (0x80FFF000): 1 for a pass, else a check number * 2 + 1. */
#include <stdint.h>
#define R(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define OUT 0x80FF0300u
#define TOHOST 0x80FFF000u
#define VA 0x40000000u
#define SUMBIT 0x40000u
#define FLAGS 0xCFu
#define UFLAGS 0xDFu /* V R W X U A D */

static inline uint32_t rd_sstatus(void) { uint32_t v; __asm__ volatile("csrr %0, sstatus" : "=r"(v)); return v; }

__attribute__((interrupt("machine"), aligned(4))) void trap(void) {
    uint32_t c, v;
    __asm__ volatile("csrr %0, mcause" : "=r"(c));
    __asm__ volatile("csrr %0, mtval" : "=r"(v));
    R(OUT + 24) = c; R(OUT + 28) = v;
    uint32_t code = 0;
    if (R(OUT + 0) & SUMBIT) code = 1;
    else if (R(OUT + 4) & SUMBIT) code = 2;
    else if (!(R(OUT + 8) & SUMBIT)) code = 3;
    else if (R(OUT + 12) != 0xCAFE0001u) code = 4;
    else if (!(R(OUT + 16) & SUMBIT)) code = 5;
    else if (R(OUT + 20) & SUMBIT) code = 6;
    else if (c != 13) code = 7;
    else if (v != VA) code = 8;
    R(TOHOST) = code ? code * 2 + 1 : 1;
    for (;;) ;
}

__attribute__((noreturn)) static void smain(void) {
    uint32_t old;
    R(OUT + 0) = rd_sstatus();
    __asm__ volatile("csrrs %0, sstatus, %1" : "=r"(old) : "r"(SUMBIT));
    R(OUT + 4) = old;
    R(OUT + 8) = rd_sstatus();
    R(OUT + 12) = R(VA);
    __asm__ volatile("csrrc %0, sstatus, %1" : "=r"(old) : "r"(SUMBIT));
    R(OUT + 16) = old;
    R(OUT + 20) = rd_sstatus();
    (void)R(VA); /* must fault */
    R(TOHOST) = 99 * 2 + 1; /* no fault: wrong */
    for (;;) ;
}

void main(void) {
    uint32_t root = 0x80100000u, l2 = root + 0x1000u;
    for (uint32_t i = 0; i < 1024; i++) { R(root + 4 * i) = 0; R(l2 + 4 * i) = 0; }
    R(root + 4 * 0x200) = (0x80000000u >> 2) | FLAGS;
    R(root + 4 * 0x203) = (0x80C00000u >> 2) | FLAGS;
    R(root + 4 * (VA >> 22)) = ((l2 >> 12) << 10) | 1u;
    R(l2) = ((0x80400000u >> 12) << 10) | UFLAGS;
    R(0x80400000u) = 0xCAFE0001u;
    __asm__ volatile("csrw satp, %0" :: "r"(0x80000000u | root >> 12));
    __asm__ volatile("sfence.vma");
    uint32_t ms;
    __asm__ volatile("csrr %0, mstatus" : "=r"(ms));
    ms = (ms & ~0x1800u) | 0x0800u;
    __asm__ volatile("csrw mstatus, %0" :: "r"(ms));
    __asm__ volatile("csrw mepc, %0" :: "r"(smain));
    __asm__ volatile("csrw mtvec, %0" :: "r"(trap));
    __asm__ volatile("mret");
    for (;;) ;
}
