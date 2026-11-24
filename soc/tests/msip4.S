# Quad-core software-interrupt ping-pong. The CLINT msip word of hart h is at 0x02000000 + 4h. mip bit 3 is the hart's own msip.
# Hart 0 raises msip[1]; hart 1 sees it in mip, clears msip[1] and raises msip[0]; hart 0 sees it, clears msip[0], counts a round.
# Ten rounds. Hart 0 stores the round count at 0x80001200 and the flag 0x600D at 0x80001204. Harts 2 and 3 park.
	.section .text
	.globl _start
_start:
	csrr t0, mhartid
	li s0, 0x02000000
	li s1, 10
	beqz t0, h0
	li t1, 1
	beq t0, t1, h1
	j park
h0:
	li t0, 1
	sw t0, 4(s0)
w0:	csrr t2, mip
	andi t2, t2, 8
	beqz t2, w0
	sw zero, 0(s0)
	li t3, 0x80001200
	lw t4, 0(t3)
	addi t4, t4, 1
	sw t4, 0(t3)
	addi s1, s1, -1
	bnez s1, h0
	li t5, 0x600D
	sw t5, 4(t3)
	j park
h1:
w1:	csrr t2, mip
	andi t2, t2, 8
	beqz t2, w1
	sw zero, 4(s0)
	li t0, 1
	sw t0, 0(s0)
	addi s1, s1, -1
	bnez s1, w1
park:	j park
