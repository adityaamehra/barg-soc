# Quad-core timer interrupts. Each hart enables MTIE and MIE and arms mtimecmp[h] = mtime + 300 + 64h (the CLINT is at 0x02000000;
# mtimecmp of hart h at 0x02004000 + 8h; mtime at 0x0200BFF8). The handler disables its mtimecmp, records mcause at 0x80001400 + 4h and
# the mtime it saw at 0x80001410 + 4h; the programmed value is at 0x80001420 + 4h. Any other trap: 0x80001430 (must stay 0).
	.section .text
	.globl _start
_start:
	la t0, handler
	csrw mtvec, t0
	li t0, 0x80
	csrw mie, t0
	csrsi mstatus, 8
	csrr t0, mhartid
	li t1, 0x0200BFF8
	lw t2, 0(t1)
	addi t2, t2, 300
	slli t3, t0, 6
	add t2, t2, t3
	slli t3, t0, 2
	li t4, 0x80001420
	add t4, t4, t3
	sw t2, 0(t4)
	slli t5, t0, 3
	li t6, 0x02004000
	add t5, t5, t6
	sw zero, 4(t5)
	sw t2, 0(t5)
idle:	j idle

	.align 4
handler:
	csrr t0, mcause
	li t1, 0x80000007
	bne t0, t1, bad
	csrr t0, mhartid
	slli t3, t0, 3
	li t6, 0x02004000
	add t5, t3, t6
	li t1, -1
	sw t1, 4(t5)
	sw t1, 0(t5)
	slli t3, t0, 2
	li t4, 0x80001400
	add t4, t4, t3
	li t1, 0x80000007
	sw t1, 0(t4)
	li t4, 0x80001410
	add t4, t4, t3
	li t6, 0x0200BFF8
	lw t2, 0(t6)
	sw t2, 0(t4)
	mret
bad:
	li t4, 0x80001430
	li t5, 0xBAD
	sw t5, 0(t4)
	mret
