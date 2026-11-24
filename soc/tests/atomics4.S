# Quad-core atomics test. All four harts run this program from reset.
#  part A: 100 x amoadd.w of 1 into counter A (0x80001000)            -> counter A = 400
#  part B: 100 times, under an LR/SC spinlock (0x80001008), a plain read-modify-write of counter B (0x80001010) -> counter B = 400
#  barrier: each hart adds 1 to done (0x80001004) twice; hart 0 waits for done == 8, then stores A at 0x80001100 and B at 0x80001104.
	.section .text
	.globl _start
_start:
	csrr t0, mhartid
	li t1, 0x80001000
	li t2, 0x80001004
	li t3, 100
1:	li t4, 1
	amoadd.w zero, t4, (t1)
	addi t3, t3, -1
	bnez t3, 1b
	li t4, 1
	amoadd.w zero, t4, (t2)
	li t3, 100
	li t5, 0x80001008
	li t6, 0x80001010
2:	lr.w a1, (t5)
	bnez a1, 2b
	li a2, 1
	sc.w a3, a2, (t5)
	bnez a3, 2b
	lw a4, 0(t6)
	addi a4, a4, 1
	sw a4, 0(t6)
	fence rw, rw
	sw zero, 0(t5)
	addi t3, t3, -1
	bnez t3, 2b
	li t4, 1
	amoadd.w zero, t4, (t2)
	bnez t0, park
3:	lw t4, 0(t2)
	li t3, 8
	bne t4, t3, 3b
	lw a0, 0(t1)
	sw a0, 0x100(t1)
	lw a5, 0(t6)
	sw a5, 0x104(t1)
park:	j park
