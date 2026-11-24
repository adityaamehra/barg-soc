# Quad-core external interrupts through the PLIC (base 0x0C000000). Sources 2 and 3 are the pins ext_s2 and ext_s3 (the testbench drives them).
# Hart 0 sets priority(src 2) = 2 and priority(src 3) = 5. Each hart h sets its own context: enable mask and threshold
#   hart 0: src 2, threshold 2 (priority 2 is not above it: masked)   hart 1: src 2 and 3, threshold 7 (masked)
#   hart 2: src 2, threshold 0                                        hart 3: src 3, threshold 0
# and counts itself ready at 0x80001500. A hart's handler (mcause 0x8000000B) claims (0x0C200004 + 0x2000h), records the id at 0x80001510
# + 4h, counts at 0x80001520 + 4h, waits for the testbench to set 0x80001540 (it has released the pin), completes (writes the id back) and
# counts at 0x80001560. Any other trap: 0x80001550 (must stay 0).
	.section .text
	.globl _start
_start:
	la t0, handler
	csrw mtvec, t0
	li t0, 0x800
	csrw mie, t0
	csrsi mstatus, 8
	csrr t0, mhartid
	bnez t0, cfg
	li t1, 0x0C000000
	li t2, 2
	sw t2, 8(t1)
	li t2, 5
	sw t2, 12(t1)
cfg:
	slli t3, t0, 8	# PLIC context 2h is the machine context of hart h (8 contexts)
	li t4, 0x0C002000
	add t4, t4, t3
	slli t3, t0, 13
	li t5, 0x0C200000
	add t5, t5, t3
	li t1, 1
	beq t0, t1, c1
	li t1, 2
	beq t0, t1, c2
	li t1, 3
	beq t0, t1, c3
	li t6, 0x4
	li t2, 2
	j wr
c1:	li t6, 0xC
	li t2, 7
	j wr
c2:	li t6, 0x4
	li t2, 0
	j wr
c3:	li t6, 0x8
	li t2, 0
wr:	sw t6, 0(t4)
	sw t2, 0(t5)
	li t1, 0x80001500
	li t2, 1
	amoadd.w zero, t2, (t1)
idle:	j idle

	.align 4
handler:
	csrr t0, mcause
	li t1, 0x8000000B
	bne t0, t1, bad
	csrr t0, mhartid
	slli t3, t0, 13
	li t4, 0x0C200004
	add t4, t4, t3
	lw t5, 0(t4)
	slli t3, t0, 2
	li t6, 0x80001510
	add t6, t6, t3
	sw t5, 0(t6)
	li t6, 0x80001520
	add t6, t6, t3
	lw t1, 0(t6)
	addi t1, t1, 1
	sw t1, 0(t6)
	beqz t5, out
	li t6, 0x80001540
1:	lw t1, 0(t6)
	beqz t1, 1b
	sw t5, 0(t4)
	li t6, 0x80001560
	li t1, 1
	amoadd.w zero, t1, (t6)
out:	mret
bad:
	li t4, 0x80001550
	li t5, 0xBAD
	sw t5, 0(t4)
	mret
