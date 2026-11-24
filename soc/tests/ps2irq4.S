# PS/2 keyboard and mouse through the PLIC (sources 4 and 5): hart 0 polls the keyboard reset reply, takes the mouse bytes by machine external
# interrupts (PLIC context 0), then drops to supervisor mode and takes a keyboard byte by a supervisor external interrupt (context 1, mideleg bit 9).
# Registers (Altera UP layout): DATA at +0 (read: avail<<16 | valid<<15 | byte, pops), CONTROL at +4 (bit 0 RE). Keyboard 0x10010300, mouse 0x10010400.
# Results (word index from 0x8000_0000 / 4): 0x580,0x581 keyboard reset reply (FA AA), 0x582 mouse ack of F4 (FA), 0x588 mouse ready flag,
# 0x589 keyboard ready flag, 0x58A S interrupt count, 0x58B scause, 0x58C claim id, 0x58D key byte, 0x58E..0x590 mouse bytes, 0x591 mouse claim id,
# 0x592 M interrupt count, 0x59E stray trap (must stay 0), 0x59F done flag 0x600D.
	.section .text
	.globl _start
_start:
	csrr t0, mhartid
	bnez t0, park
	la t0, mhandler
	csrw mtvec, t0
	li t0, -1
	csrw pmpaddr0, t0
	li t0, 0x1f
	csrw pmpcfg0, t0
	li t1, 0x0C000000
	li t2, 1
	sw t2, 16(t1)
	sw t2, 20(t1)
	li t1, 0x0C002000
	li t2, 0x20
	sw t2, 0(t1)
	li t1, 0x0C002080
	li t2, 0x10
	sw t2, 0(t1)
	li s0, 0x10010300
	li s1, 0x10010400
	li s2, 0x80001600
	li t0, 0xFF
	sw t0, 0(s0)
	mv a1, s0
	jal ra, rdb
	sw a0, 0(s2)
	mv a1, s0
	jal ra, rdb
	sw a0, 4(s2)
	li t0, 0xF4
	sw t0, 0(s1)
	mv a1, s1
	jal ra, rdb
	sw a0, 8(s2)
	li t0, 1
	sw t0, 4(s1)
	li t0, 1
	sw t0, 0x20(s2)
	li t0, 0x800
	csrw mie, t0
	csrsi mstatus, 8
mwait:
	lw s3, 0x48(s2)
	li s4, 3
	bltu s3, s4, mwait
	csrci mstatus, 8
	csrw mie, zero
	sw zero, 4(s1)
	li t0, 0x200
	csrw mideleg, t0
	la t0, shandler
	csrw stvec, t0
	li t0, 0x200
	csrw mie, t0
	li t0, 0x1800
	csrc mstatus, t0
	li t0, 0x0800
	csrs mstatus, t0
	la t0, smain
	csrw mepc, t0
	mret
smain:
	csrsi sstatus, 2
	li t0, 1
	sw t0, 4(s0)
	sw t0, 0x24(s2)
swait:
	lw s3, 0x28(s2)
	li s4, 24
	bltu s3, s4, swait
	li t0, 60000
1:	addi t0, t0, -1
	bnez t0, 1b
	li t0, 0x600D
	sw t0, 0x7C(s2)
end:	j end
park:	j park

rdb:	lw a0, 0(a1)
	li t6, 0x8000
	and t6, a0, t6
	beqz t6, rdb
	andi a0, a0, 0xff
	ret

	.align 4
mhandler:
	csrr t5, mcause
	li t6, 0x8000000B
	bne t5, t6, mbad
	li t5, 0x0C200004
	lw t4, 0(t5)
	li t6, 0x80001644
	sw t4, 0(t6)
	li t3, 0x10010400
	lw t2, 0(t3)
	andi t2, t2, 0xff
	li t6, 0x80001648
	lw t1, 0(t6)
	slli t0, t1, 2
	li t6, 0x80001638
	add t6, t6, t0
	sw t2, 0(t6)
	addi t1, t1, 1
	li t6, 0x80001648
	sw t1, 0(t6)
	sw t4, 0(t5)
	mret
mbad:	li t6, 0x80001678
	sw t5, 0(t6)
1:	j 1b

	.align 4
shandler:	# like Linux's plic_handle_irq: clear sie.SEIE, claim until 0 (read the data, complete each), set sie.SEIE again
	csrr t5, scause
	li t4, 0x8000162C
	sw t5, 0(t4)
	li t6, 0x80000009
	bne t5, t6, sbad
	li t6, 0x80001658
	lw t1, 0(t6)
	addi t1, t1, 1
	sw t1, 0(t6)
	li t6, 0x200
	csrc sie, t6
sclaim:	li t5, 0x0C201004
	lw t4, 0(t5)
	beqz t4, sdone
	li t6, 0x80001630
	sw t4, 0(t6)
	li t3, 0x10010300
	lw t2, 0(t3)
	andi t2, t2, 0xff
	li t6, 0x80001634
	sw t2, 0(t6)
	sw t4, 0(t5)
	li t6, 0x80001628
	lw t1, 0(t6)
	slli t0, t1, 2
	li t3, 0x80001700
	add t3, t3, t0
	ori t2, t2, 0x100
	sw t2, 0(t3)
	addi t1, t1, 1
	sw t1, 0(t6)
	j sclaim
sdone:	li t6, 0x200
	csrs sie, t6
	sret
sbad:	li t6, 0x80001678
	sw t5, 0(t6)
1:	j 1b
