"""A small two-pass assembler for the GPU's tests: RV32IM, the CSR reads and the SIMT and tensor instructions of ISA.md.

    a = Asm()
    a.li("t0", 4); a.label("loop"); a.addi("t0", "t0", -1); a.bnez("t0", "loop"); a.tmc("zero")
    code = a.assemble()        # bytes, little-endian, origin 0

It exists so the model's unit tests need no compiler; kernels written in C go through riscv64-elf-gcc (sw/).
"""

from __future__ import annotations

import simt

ABI = ["zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2", "s0", "s1"] + [f"a{i}" for i in range(8)] + \
      [f"s{i}" for i in range(2, 12)] + [f"t{i}" for i in range(3, 7)]
REG = {name: i for i, name in enumerate(ABI)} | {f"x{i}": i for i in range(32)} | {"fp": 8}
CSR = {"tid": simt.CSR_TID, "wid": simt.CSR_WID, "cid": simt.CSR_CID, "tmask": simt.CSR_TMASK, "gtid": simt.CSR_GTID,
       "karg": simt.CSR_KARG, "nt": simt.CSR_NT, "nw": simt.CSR_NW, "nc": simt.CSR_NC, "cycle": simt.CSR_CYCLE,
       "instret": simt.CSR_INSTRET}


def r(name) -> int:
    return name if isinstance(name, int) else REG[name]


def enc_r(op, rd, f3, rs1, rs2, f7):
    return f7 << 25 | r(rs2) << 20 | r(rs1) << 15 | f3 << 12 | r(rd) << 7 | op


def enc_i(op, rd, f3, rs1, imm):
    assert -2048 <= imm < 2048, imm
    return (imm & 0xFFF) << 20 | r(rs1) << 15 | f3 << 12 | r(rd) << 7 | op


def enc_s(op, f3, rs1, rs2, imm):
    assert -2048 <= imm < 2048, imm
    imm &= 0xFFF
    return (imm >> 5) << 25 | r(rs2) << 20 | r(rs1) << 15 | f3 << 12 | (imm & 31) << 7 | op


def enc_b(f3, rs1, rs2, off):
    assert -4096 <= off < 4096 and off % 2 == 0, off
    off &= 0x1FFF
    return (off >> 12 & 1) << 31 | (off >> 5 & 0x3F) << 25 | r(rs2) << 20 | r(rs1) << 15 | f3 << 12 | \
        (off >> 1 & 0xF) << 8 | (off >> 11 & 1) << 7 | 0x63


def enc_j(rd, off):
    off &= 0x1FFFFF
    return (off >> 20 & 1) << 31 | (off >> 1 & 0x3FF) << 21 | (off >> 11 & 1) << 20 | (off >> 12 & 0xFF) << 12 | r(rd) << 7 | 0x6F


class Asm:
    def __init__(self, origin: int = 0):
        self.origin = origin
        self.items: list = []       # int (encoded) or (callable(pc, labels) -> int)
        self.labels: dict[str, int] = {}

    @property
    def pc(self) -> int:
        return self.origin + 4 * len(self.items)

    def label(self, name: str) -> None:
        self.labels[name] = self.pc

    def word(self, w) -> None:
        self.items.append(w)

    def assemble(self) -> bytes:
        out = bytearray()
        for i, it in enumerate(self.items):
            w = it(self.origin + 4 * i, self.labels) if callable(it) else it
            out += (w & 0xFFFFFFFF).to_bytes(4, "little")
        return bytes(out)

    # RV32I
    def lui(self, rd, imm20): self.word(imm20 << 12 & 0xFFFFF000 | r(rd) << 7 | 0x37)
    def auipc(self, rd, imm20): self.word(imm20 << 12 & 0xFFFFF000 | r(rd) << 7 | 0x17)

    def li(self, rd, value):
        value &= 0xFFFFFFFF
        lo = value & 0xFFF
        lo = lo - 4096 if lo >= 2048 else lo
        hi = (value - lo) >> 12 & 0xFFFFF
        if hi:
            self.lui(rd, hi)
            if lo:
                self.addi(rd, rd, lo)
        else:
            self.addi(rd, "zero", lo)

    def la(self, rd, label):
        """Absolute address of a label (2 words): lui + addi, resolved at the end."""
        def hi(pc, labels):
            v = labels[label]; lo = v & 0xFFF; lo = lo - 4096 if lo >= 2048 else lo
            return ((v - lo) >> 12 & 0xFFFFF) << 12 | r(rd) << 7 | 0x37
        def lo(pc, labels):
            v = labels[label] & 0xFFF
            return enc_i(0x13, rd, 0, rd, v - 4096 if v >= 2048 else v)
        self.word(hi); self.word(lo)

    def jal(self, rd, label): self.word(lambda pc, L: enc_j(rd, L[label] - pc))
    def j(self, label): self.jal("zero", label)
    def jalr(self, rd, rs1, imm=0): self.word(enc_i(0x67, rd, 0, rs1, imm))
    def ret(self): self.jalr("zero", "ra")

    def _br(self, f3, a, b, label): self.word(lambda pc, L: enc_b(f3, a, b, L[label] - pc))
    def beq(self, a, b, l): self._br(0, a, b, l)
    def bne(self, a, b, l): self._br(1, a, b, l)
    def blt(self, a, b, l): self._br(4, a, b, l)
    def bge(self, a, b, l): self._br(5, a, b, l)
    def bltu(self, a, b, l): self._br(6, a, b, l)
    def bgeu(self, a, b, l): self._br(7, a, b, l)
    def beqz(self, a, l): self.beq(a, "zero", l)
    def bnez(self, a, l): self.bne(a, "zero", l)

    def lb(self, rd, off, rs1): self.word(enc_i(0x03, rd, 0, rs1, off))
    def lh(self, rd, off, rs1): self.word(enc_i(0x03, rd, 1, rs1, off))
    def lw(self, rd, off, rs1): self.word(enc_i(0x03, rd, 2, rs1, off))
    def lbu(self, rd, off, rs1): self.word(enc_i(0x03, rd, 4, rs1, off))
    def lhu(self, rd, off, rs1): self.word(enc_i(0x03, rd, 5, rs1, off))
    def sb(self, rs2, off, rs1): self.word(enc_s(0x23, 0, rs1, rs2, off))
    def sh(self, rs2, off, rs1): self.word(enc_s(0x23, 1, rs1, rs2, off))
    def sw(self, rs2, off, rs1): self.word(enc_s(0x23, 2, rs1, rs2, off))

    def addi(self, rd, rs1, imm): self.word(enc_i(0x13, rd, 0, rs1, imm))
    def slti(self, rd, rs1, imm): self.word(enc_i(0x13, rd, 2, rs1, imm))
    def sltiu(self, rd, rs1, imm): self.word(enc_i(0x13, rd, 3, rs1, imm))
    def xori(self, rd, rs1, imm): self.word(enc_i(0x13, rd, 4, rs1, imm))
    def ori(self, rd, rs1, imm): self.word(enc_i(0x13, rd, 6, rs1, imm))
    def andi(self, rd, rs1, imm): self.word(enc_i(0x13, rd, 7, rs1, imm))
    def slli(self, rd, rs1, sh): self.word(enc_r(0x13, rd, 1, rs1, sh, 0))
    def srli(self, rd, rs1, sh): self.word(enc_r(0x13, rd, 5, rs1, sh, 0))
    def srai(self, rd, rs1, sh): self.word(enc_r(0x13, rd, 5, rs1, sh, 0x20))
    def mv(self, rd, rs): self.addi(rd, rs, 0)
    def nop(self): self.addi("zero", "zero", 0)

    def _op(self, f3, f7, rd, a, b): self.word(enc_r(0x33, rd, f3, a, b, f7))
    def add(self, rd, a, b): self._op(0, 0, rd, a, b)
    def sub(self, rd, a, b): self._op(0, 0x20, rd, a, b)
    def sll(self, rd, a, b): self._op(1, 0, rd, a, b)
    def slt(self, rd, a, b): self._op(2, 0, rd, a, b)
    def sltu(self, rd, a, b): self._op(3, 0, rd, a, b)
    def xor(self, rd, a, b): self._op(4, 0, rd, a, b)
    def srl(self, rd, a, b): self._op(5, 0, rd, a, b)
    def sra(self, rd, a, b): self._op(5, 0x20, rd, a, b)
    def or_(self, rd, a, b): self._op(6, 0, rd, a, b)
    def and_(self, rd, a, b): self._op(7, 0, rd, a, b)
    def mul(self, rd, a, b): self._op(0, 1, rd, a, b)
    def mulh(self, rd, a, b): self._op(1, 1, rd, a, b)
    def mulhsu(self, rd, a, b): self._op(2, 1, rd, a, b)
    def mulhu(self, rd, a, b): self._op(3, 1, rd, a, b)
    def div(self, rd, a, b): self._op(4, 1, rd, a, b)
    def divu(self, rd, a, b): self._op(5, 1, rd, a, b)
    def rem(self, rd, a, b): self._op(6, 1, rd, a, b)
    def remu(self, rd, a, b): self._op(7, 1, rd, a, b)

    def csrr(self, rd, csr):
        self.word(enc_i(0x73, rd, 2, "zero", 0) | (CSR[csr] if isinstance(csr, str) else csr) << 20)

    def raw(self, w): self.word(w)

    # SIMT (ISA.md)
    def tmc(self, rs1): self.word(enc_r(simt.OP_CUSTOM0, 0, simt.F3_TMC, rs1, 0, 0))
    def wspawn(self, rs1, rs2): self.word(enc_r(simt.OP_CUSTOM0, 0, simt.F3_WSPAWN, rs1, rs2, 0))
    def split(self, rs1): self.word(enc_r(simt.OP_CUSTOM0, 0, simt.F3_SPLIT, rs1, 0, 0))
    def join(self): self.word(enc_r(simt.OP_CUSTOM0, 0, simt.F3_JOIN, 0, 0, 0))
    def bar(self, rs1, rs2): self.word(enc_r(simt.OP_CUSTOM0, 0, simt.F3_BAR, rs1, rs2, 0))
    def vote(self, mode, rd, rs1): self.word(enc_r(simt.OP_CUSTOM0, rd, simt.F3_VOTE, rs1, 0, mode))
    def shfl(self, mode, rd, rs1, rs2): self.word(enc_r(simt.OP_CUSTOM0, rd, simt.F3_SHFL, rs1, rs2, mode))
    def mma(self, rs1, rs2): self.word(enc_r(simt.OP_CUSTOM1, 0, simt.F3_MMA_I8, rs1, rs2, 0))
    def mma_ld(self, rd, rs1): self.word(enc_r(simt.OP_CUSTOM1, rd, simt.F3_MMA_LD, rs1, 0, 0))
    def mma_st(self, rs1, rs2): self.word(enc_r(simt.OP_CUSTOM1, 0, simt.F3_MMA_ST, rs1, rs2, 0))
    def mma_zero(self): self.word(enc_r(simt.OP_CUSTOM1, 0, simt.F3_MMA_ZERO, 0, 0, 0))

    # graphics (gfx/, opcode custom-2)
    def gfx_cfg(self, rs1, rs2): self.word(enc_r(simt.OP_CUSTOM2, 0, simt.F3_GFX_CFG, rs1, rs2, 0))
    def pix(self, rs1, rs2): self.word(enc_r(simt.OP_CUSTOM2, 0, simt.F3_GFX_PIX, rs1, rs2, 0))
