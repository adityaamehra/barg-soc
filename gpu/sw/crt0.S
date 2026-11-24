/* Start-up for the BARG SIMT GPU (demos/simt-gpu/ISA.md). The host starts warp 0 with lane 0 active at _start.
 * Warp 0 spawns the other warps at _warp_start; every warp then turns on all its lanes, gives each thread its own stack
 * (the top of global memory, __stack_size bytes per thread, by global thread id), calls kernel(), and ends with tmc 0. */
    .section .text.init
    .globl _start
_start:
    csrr    t0, 0xFC1                 /* nw */
    la      t1, _warp_start
    .insn r 0x0B, 1, 0, x0, t0, t1    /* wspawn nw, _warp_start */
_warp_start:
    csrr    t0, 0xFC0                 /* nt */
    li      t1, 1
    sll     t1, t1, t0
    addi    t1, t1, -1
    .insn r 0x0B, 0, 0, x0, t1, x0    /* tmc: every lane */
    csrr    t0, 0xCC4                 /* gtid */
    la      t1, __stack_size
    mul     t0, t0, t1
    la      sp, __stack_top
    sub     sp, sp, t0
    li      ra, 0
    call    kernel
    .insn r 0x0B, 0, 0, x0, x0, x0    /* tmc 0: this warp is done */
