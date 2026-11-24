# Quad-core software-interrupt ping-pong, trap-driven. Harts 0 and 1 enable MSIE and MIE and take machine software interrupts.
# Hart 1 signals ready at 0x80001210; hart 0 then raises msip[1]. Hart 1's handler clears msip[1], raises msip[0], counts (0x80001208).
# Hart 0's handler clears msip[0], counts (0x80001200), and raises msip[1] again unless it has counted 10; on the 10th it stores 0x600D
# at 0x80001204. Any trap that is not a machine software interrupt is counted at 0x80001218 (must stay 0).
	.section .text
	.globl _start
_start:
	la t0, handler
	csrw mtvec, t0
	li t0, 8
	csrw mie, t0
	csrsi mstatus, 8
	csrr t0, mhartid
	li t1, 1
	beq t0, t1, hart1
	bnez t0, idle
	li t1, 0x80001210
w0:	lw t2, 0(t1)
	beqz t2, w0
	li t2, 0x02000000
	li t3, 1
	sw t3, 4(t2)
	j idle
hart1:
	li t1, 0x80001210
	li t2, 1
	sw t2, 0(t1)
idle:	j idle

	.align 4
handler:
	csrr t0, mcause
	li t1, 0x80000003
	bne t0, t1, bad
	csrr t0, mhartid
	li t2, 0x02000000
	bnez t0, h1_handle
	sw zero, 0(t2)
	li t4, 0x80001200
	lw t5, 0(t4)
	addi t5, t5, 1
	sw t5, 0(t4)
	li t6, 10
	bge t5, t6, h0_done
	li t3, 1
	sw t3, 4(t2)
	mret
h0_done:
	li t3, 0x600D
	sw t3, 4(t4)
	mret
h1_handle:
	sw zero, 4(t2)
	li t3, 1
	sw t3, 0(t2)
	li t4, 0x80001208
	lw t5, 0(t4)
	addi t5, t5, 1
	sw t5, 0(t4)
	mret
bad:
	li t4, 0x80001218
	li t5, 0xBAD
	sw t5, 0(t4)
	mret
