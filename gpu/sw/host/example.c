/* A management-core program that runs the GPU's vecadd kernel. Build: riscv64-elf-gcc -march=rv32im_zicsr -mabi=ilp32 -c example.c
 *
 * Where a kernel's arrays live is in its ELF: `riscv64-elf-nm -S vecadd.elf`. For sw/kernels/vecadd.c the linker puts n at global
 * memory byte 0x000, c at 0x004, a at 0x324 and b at 0x644 (global memory starts at 0x1000_0000 for the GPU, offset 0 here).
 * The program's words are the ELF's text: `riscv64-elf-objcopy -O binary -j .text vecadd.elf vecadd.bin`, then embedded as an array. */
#include "gpu_host.h"

extern const uint32_t vecadd_text[], vecadd_text_words;

int run_vecadd(const uint32_t *a, const uint32_t *b, uint32_t *c, unsigned n) {
    gpu_write_imem(0, vecadd_text, (unsigned)vecadd_text_words);
    GPU_GLOBAL[0x000 / 4] = n;
    gpu_write_global(0x324 / 4, a, n);
    gpu_write_global(0x644 / 4, b, n);
    gpu_start(0, 0);
    if (gpu_wait() & GPU_ERROR) return -(int)gpu_error_cause();
    gpu_read_global(0x004 / 4, c, n);
    return 0;
}
