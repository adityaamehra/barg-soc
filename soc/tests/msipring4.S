# Quad-core software-interrupt ring, trap-driven, all four harts. Each hart enables MSIE and MIE; hart 0 raises msip[1] once all are ready.
# A hart's handler clears its own msip, counts at 0x80001310 + 4h, and raises msip[(h+1) & 3]; hart 0 stops after counting 5 and stores
# 0x600D at 0x80001320. Any other trap is counted at 0x80001330 (must stay 0). Expected: every count 5, flag 0x600D.
	.section .text
	.globl _start
_start:
	la t0, handler
	csrw mtvec, t0
	li t0, 8
	csrw mie, t0
	csrsi mstatus, 8
	csrr t0, mhartid
	li t1, 0x80001300
	li t2, 1
	amoadd.w zero, t2, (t1)
	bnez t0, idle
	li t3, 4
w:	lw t2, 0(t1)
	bne t2, t3, w
	li t2, 0x02000000
	li t4, 1
	sw t4, 4(t2)
idle:	j idle

	.align 4
handler:
	csrr t0, mcause
	li t1, 0x80000003
	bne t0, t1, bad
	csrr t0, mhartid
	li t2, 0x02000000
	slli t3, t0, 2
	add t4, t2, t3
	sw zero, 0(t4)
	li t5, 0x80001310
	add t5, t5, t3
	lw t6, 0(t5)
	addi t6, t6, 1
	sw t6, 0(t5)
	bnez t0, forward
	li t1, 5
	bge t6, t1, done
forward:
	addi t4, t0, 1
	andi t4, t4, 3
	slli t4, t4, 2
	add t4, t2, t4
	li t1, 1
	sw t1, 0(t4)
	mret
done:
	li t1, 0x600D
	li t2, 0x80001320
	sw t1, 0(t2)
	mret
bad:
	li t4, 0x80001330
	li t5, 0xBAD
	sw t5, 0(t4)
	mret
