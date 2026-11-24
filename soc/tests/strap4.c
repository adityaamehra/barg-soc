/* sstatus.SUM across a supervisor trap: load page faults are delegated to S mode (medeleg bit 13). In S mode SUM is set, then a load from an
 * unmapped user page (0x40001000) faults into the S-mode handler, which reads sstatus (SUM must still be 1: a trap changes only SIE, SPIE
 * and SPP), scause (13) and stval (0x40001000), and clears SUM with csrrc, which must return the old value (SUM = 1).
 * Results at 0x80FF0300..: [0] sstatus in the handler [1] scause [2] stval [3] csrrc's old value.  TOHOST: 1 pass, else check * 2 + 1. */
#include <stdint.h>
#define R(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define OUT 0x80FF0300u
#define TOHOST 0x80FFF000u
#define VA 0x40000000u
#define SUMBIT 0x40000u
#define FLAGS 0xCFu
#define UFLAGS 0xDFu /* V R W X U A D */

static inline uint32_t rd_sstatus(void) { uint32_t v; __asm__ volatile("csrr %0, sstatus" : "=r"(v)); return v; }

__attribute__((interrupt("supervisor"), aligned(4))) void strap(void) {
    uint32_t st, c, v, old;
    st = rd_sstatus();
    __asm__ volatile("csrr %0, scause" : "=r"(c));
    __asm__ volatile("csrr %0, stval" : "=r"(v));
    __asm__ volatile("csrrc %0, sstatus, %1" : "=r"(old) : "r"(SUMBIT));
    R(OUT + 0) = st; R(OUT + 4) = c; R(OUT + 8) = v; R(OUT + 12) = old;
    uint32_t code = 0;
    if (c != 13) code = 1;
    else if (v != 0x40001000u) code = 2;
    else if (!(st & SUMBIT)) code = 3;
    else if (!(old & SUMBIT)) code = 4;
    R(TOHOST) = code ? code * 2 + 1 : 1;
    for (;;) ;
}

__attribute__((noreturn)) static void smain(void) {
    __asm__ volatile("csrs sstatus, %0" :: "r"(SUMBIT));
    (void)R(0x40001000u); /* unmapped: faults into strap */
    R(TOHOST) = 99 * 2 + 1;
    for (;;) ;
}

void main(void) {
    uint32_t root = 0x80100000u, l2 = root + 0x1000u;
    for (uint32_t i = 0; i < 1024; i++) { R(root + 4 * i) = 0; R(l2 + 4 * i) = 0; }
    R(root + 4 * 0x200) = (0x80000000u >> 2) | FLAGS;
    R(root + 4 * 0x203) = (0x80C00000u >> 2) | FLAGS;
    R(root + 4 * (VA >> 22)) = ((l2 >> 12) << 10) | 1u;
    R(l2) = ((0x80400000u >> 12) << 10) | UFLAGS; /* page 0 only; page 1 (0x40001000) stays unmapped */
    __asm__ volatile("csrw medeleg, %0" :: "r"(1u << 13));
    __asm__ volatile("csrw stvec, %0" :: "r"(strap));
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
