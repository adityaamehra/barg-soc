/* Host-side driver for the SIMT GPU on Caravel: runs on the management core (RISC-V, ilp32) and talks to the user project through
 * its Wishbone window at 0x3000_0000 (see demos/simt-gpu/README.md, section 7). Word accesses only.
 *
 *     static const uint32_t program[] = { ... };            // the GPU kernel's text, words (riscv64-elf-gcc -> objcopy)
 *     gpu_write_imem(0, program, sizeof program / 4);
 *     gpu_write_global(0, input, n);                         // byte offset into the 8 KB global memory
 *     gpu_start(0, 0);                                       // start pc, kernel argument
 *     uint32_t status = gpu_wait();                          // polls STATUS: returns GPU_DONE or GPU_ERROR
 *     if (status & GPU_ERROR) { cause = gpu_error_cause(); pc = gpu_error_pc(); }
 *     gpu_read_global(0, output, m);
 *
 * Or enable the user_irq[0] (done) / user_irq[1] (error) interrupts in the management SoC and wait for them instead of polling.
 */
#ifndef GPU_HOST_H
#define GPU_HOST_H

#include <stdint.h>

#define GPU_BASE        0x30000000u
#define GPU_CTRL_REG    (*(volatile uint32_t *)(GPU_BASE + 0x00))   /* write 1 to start (ignored while running) */
#define GPU_START_PC    (*(volatile uint32_t *)(GPU_BASE + 0x04))
#define GPU_KARG        (*(volatile uint32_t *)(GPU_BASE + 0x08))
#define GPU_STATUS      (*(volatile uint32_t *)(GPU_BASE + 0x0C))
#define GPU_ERR_PC      (*(volatile uint32_t *)(GPU_BASE + 0x10))
#define GPU_ERR_INFO    (*(volatile uint32_t *)(GPU_BASE + 0x14))
#define GPU_IMEM        ((volatile uint32_t *)(GPU_BASE + 0x10000))  /* 2 KB, write only */
#define GPU_GLOBAL      ((volatile uint32_t *)(GPU_BASE + 0x20000))  /* 8 KB */
#define GPU_SHARED      ((volatile uint32_t *)(GPU_BASE + 0x30000))  /* 4 KB */

#define GPU_RUNNING     0x1u
#define GPU_DONE        0x2u
#define GPU_ERROR       0x4u

static inline void gpu_write_imem(unsigned word_off, const uint32_t *w, unsigned n) {
    for (unsigned i = 0; i < n; i++) GPU_IMEM[word_off + i] = w[i];
}
static inline void gpu_write_global(unsigned word_off, const uint32_t *w, unsigned n) {
    for (unsigned i = 0; i < n; i++) GPU_GLOBAL[word_off + i] = w[i];
}
static inline void gpu_read_global(unsigned word_off, uint32_t *w, unsigned n) {
    for (unsigned i = 0; i < n; i++) w[i] = GPU_GLOBAL[word_off + i];
}
static inline void gpu_start(uint32_t pc, uint32_t karg) {
    GPU_START_PC = pc;
    GPU_KARG = karg;
    GPU_CTRL_REG = 1;
}
/* Poll until the core is done or stopped on an error; returns GPU_DONE or GPU_ERROR. */
static inline uint32_t gpu_wait(void) {
    uint32_t s;
    while (!((s = GPU_STATUS) & (GPU_DONE | GPU_ERROR))) { }
    return s & (GPU_DONE | GPU_ERROR);
}
static inline unsigned gpu_error_cause(void) { return GPU_ERR_INFO & 0xF; }    /* 1 illegal, 2 memory, 3 SIMT, 4 tensor, 5 CSR */
static inline unsigned gpu_error_warp(void) { return (GPU_ERR_INFO >> 8) & 3; }
static inline uint32_t gpu_error_pc(void) { return GPU_ERR_PC; }

#endif
