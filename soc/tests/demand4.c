/* Demand paging of a user page from kernel code, with the exact instruction sequence of Linux's load_elf_binary (the stack setup):
 *     csrs sstatus,a3 ; mv a0,s11 ; sw a4,0(s3) ; csrc sstatus,a3 ; bnez a0,fail ; lw s11,228(s10) ; add s3,s3,4
 * The user page (0x40002000, U=1) is not mapped at first. S mode runs the sequence with SUM set around the store; the store must raise a
 * STORE page fault (cause 15) at the sw with mtval = the address; the machine-mode handler then maps the page, sfence.vma, and returns to
 * retry the store; the rest of the sequence must then complete with no further trap, the word stored, and s3 advanced by 4.
 * Results at 0x80FF0500: [0] mcause [1] mepc [2] mtval [3] traps [4] stored word [5] s3 after.  TOHOST: 1 pass, else check * 2 + 1. */
#include <stdint.h>
#define R(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define OUT 0x80FF0500u
#define TOHOST 0x80FFF000u
#define FLAGS 0xCFu
#define UFLAGS 0xDFu
#define VA 0x40002000u
extern char sw_site[];
static const uint32_t l2base = 0x80101000u;

__attribute__((interrupt("machine"), aligned(4))) void trap(void) {
    uint32_t c, e, v;
    __asm__ volatile("csrr %0, mcause" : "=r"(c));
    __asm__ volatile("csrr %0, mepc" : "=r"(e));
    __asm__ volatile("csrr %0, mtval" : "=r"(v));
    uint32_t n = R(OUT + 12) + 1;
    R(OUT + 12) = n;
    if (n == 1) {
        R(OUT + 0) = c; R(OUT + 4) = e; R(OUT + 8) = v;
        R(l2base + 4 * 2) = ((0x80600000u >> 12) << 10) | UFLAGS; /* map VA -> 0x80600000 */
        __asm__ volatile("sfence.vma");
        return; /* retry the faulting instruction, like Linux after handle_mm_fault */
    }
    R(OUT + 28) = c; R(OUT + 32) = e; R(OUT + 36) = v; /* the second trap: cause, pc, address */
    R(TOHOST) = 3 * 2 + 1; /* a second trap */
    for (;;) ;
}

__attribute__((noreturn)) static void smain(void) {
    register uint32_t a3 __asm__("a3") = 0x40000u;
    register uint32_t a4 __asm__("a4") = 0x5A5A0001u;
    register uint32_t s3 __asm__("s3") = VA + 4;
    register uint32_t s10 __asm__("s10") = 0x80700000u;
    register uint32_t s11 __asm__("s11") = 0;
    R(0x80700000u + 228) = 0x1234u;
    __asm__ volatile(
        "csrs sstatus, a3\n"
        "mv a0, s11\n"
        ".globl sw_site\nsw_site:\n"
        "sw a4, 0(s3)\n"
        "csrc sstatus, a3\n"
        "bnez a0, 1f\n"
        "lw s11, 228(s10)\n"
        "add s3, s3, 4\n"
        "1:\n"
        : "+r"(s3), "+r"(s11) : "r"(a3), "r"(a4), "r"(s10) : "a0", "memory");
    R(OUT + 20) = s3;
    R(OUT + 24) = s11;
    uint32_t code = 0;
    if (R(OUT + 12) != 1) code = 1;
    else if (R(OUT + 0) != 15) code = 2;
    else if (R(OUT + 4) != (uint32_t)(uintptr_t)sw_site) code = 3;
    else if (R(OUT + 8) != VA + 4) code = 4;
    else if (R(0x80600004u) != 0x5A5A0001u) code = 5;
    else if (s3 != VA + 8) code = 6;
    else if (s11 != 0x1234u) code = 7;
    R(TOHOST) = code ? code * 2 + 1 : 1;
    for (;;) ;
}

void main(void) {
    uint32_t root = 0x80100000u, l2 = l2base;
    for (uint32_t i = 0; i < 1024; i++) { R(root + 4 * i) = 0; R(l2 + 4 * i) = 0; }
    R(root + 4 * 0x200) = (0x80000000u >> 2) | FLAGS;
    R(root + 4 * 0x201) = (0x80400000u >> 2) | FLAGS;
    R(root + 4 * 0x203) = (0x80C00000u >> 2) | FLAGS;
    R(root + 4 * (VA >> 22)) = ((l2 >> 12) << 10) | 1u;
    __asm__ volatile("csrw mtvec, %0" :: "r"(trap));
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
