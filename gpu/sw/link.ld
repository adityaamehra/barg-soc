/* The v0 memory map of one core (demos/simt-gpu/ISA.md): code in instruction memory; every data section in global memory
 * (instruction memory is fetch-only, so constants live there too); SIMT_SHARED arrays in shared memory; the thread stacks at
 * the top of global memory. */
OUTPUT_ARCH("riscv")
ENTRY(_start)

MEMORY
{
    imem   (rx) : ORIGIN = 0x00000000, LENGTH = 2K
    global (rw) : ORIGIN = 0x10000000, LENGTH = 8K
    shared (rw) : ORIGIN = 0x20000000, LENGTH = 4K
}

__stack_size = 128;
__threads    = 16;

SECTIONS
{
    .text : { *(.text.init) *(.text .text.*) } > imem
    .data : { *(.rodata .rodata.* .srodata .srodata.*) *(.data .data.* .sdata .sdata.*) } > global
    .bss (NOLOAD) : { *(.bss .bss.* .sbss .sbss.* COMMON) } > global
    .shared (NOLOAD) : { *(.shared) } > shared
    __stack_top = ORIGIN(global) + LENGTH(global);
    ASSERT(. <= 0x20001000, "shared memory overflow")
    ASSERT(ADDR(.bss) + SIZEOF(.bss) <= __stack_top - __threads * __stack_size, "global data overlaps the thread stacks")
    /DISCARD/ : { *(.comment) *(.riscv.attributes) *(.note*) *(.eh_frame*) }
}
