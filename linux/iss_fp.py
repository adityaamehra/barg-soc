"""RV32 F and D extensions for the instruction-level model (iss_s.py): FP registers, fflags/frm/fcsr, mstatus.FS (off, initial, clean, dirty), the FP loads and
stores (also the compressed ones) and the operations, with the arithmetic of packages/ip/tb/fpu_ref.py (the exact reference of the hardware FPU).

Written from the RISC-V unprivileged ISA (chapters F, D and C) and the privileged ISA (mstatus.FS). FS is dirty after an instruction that changes an FP register
or an exception flag, or after a write to fflags, frm or fcsr. An FP instruction, or an access to fflags, frm or fcsr, with FS off is an illegal instruction.
An fld or fsd is done as two 32-bit accesses (low word first) and must be 8-byte aligned (a misaligned one traps, as every misaligned access of this
SoC does): both words then lie in one page and a fault cannot split the instruction."""
import sys
from pathlib import Path

FS_SHIFT = 13
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "ip" / "tb"))
import fpu_ref as R  # noqa: E402

M32 = 0xFFFFFFFF
BOXED = 0xFFFFFFFF00000000


def sext(x, bits):
    return x - (1 << bits) if x >> (bits - 1) & 1 else x


def fs(m):
    return m.mstatus >> FS_SHIFT & 3


def set_dirty(m):
    m.mstatus |= 3 << FS_SHIFT


def fp_expand(half):
    """The 32-bit form of a compressed FP load or store (RV32: c.fld, c.flw, c.fsd, c.fsw, c.fldsp, c.flwsp, c.fsdsp, c.fswsp), else None."""
    q, f3 = half & 3, half >> 13 & 7
    if q == 0 and f3 in (1, 3, 5, 7):
        rs1, r2 = 8 + (half >> 7 & 7), 8 + (half >> 2 & 7)
        if f3 in (1, 5):                                                     # c.fld, c.fsd: uimm[5:3] = 12:10, uimm[7:6] = 6:5
            uimm = (half >> 10 & 7) << 3 | (half >> 5 & 3) << 6
        else:                                                                # c.flw, c.fsw: uimm[5:3] = 12:10, uimm[2] = 6, uimm[6] = 5
            uimm = (half >> 10 & 7) << 3 | (half >> 6 & 1) << 2 | (half >> 5 & 1) << 6
        width = 3 if f3 in (1, 5) else 2
        if f3 in (1, 3):
            return uimm << 20 | rs1 << 15 | width << 12 | r2 << 7 | 0x07
        return (uimm >> 5) << 25 | r2 << 20 | rs1 << 15 | width << 12 | (uimm & 31) << 7 | 0x27
    if q == 2 and f3 in (1, 3, 5, 7):
        if f3 in (1, 3):
            rd = half >> 7 & 31
            if f3 == 1:                                                      # c.fldsp: uimm[5] = 12, uimm[4:3] = 6:5, uimm[8:6] = 4:2
                uimm = (half >> 12 & 1) << 5 | (half >> 5 & 3) << 3 | (half >> 2 & 7) << 6
            else:                                                            # c.flwsp: uimm[5] = 12, uimm[4:2] = 6:4, uimm[7:6] = 3:2
                uimm = (half >> 12 & 1) << 5 | (half >> 4 & 7) << 2 | (half >> 2 & 3) << 6
            return uimm << 20 | 2 << 15 | (3 if f3 == 1 else 2) << 12 | rd << 7 | 0x07
        rs2 = half >> 2 & 31
        if f3 == 5:                                                          # c.fsdsp: uimm[5:3] = 12:10, uimm[8:6] = 9:7
            uimm = (half >> 10 & 7) << 3 | (half >> 7 & 7) << 6
        else:                                                                # c.fswsp: uimm[5:2] = 12:9, uimm[7:6] = 8:7
            uimm = (half >> 9 & 15) << 2 | (half >> 7 & 3) << 6
        return (uimm >> 5) << 25 | rs2 << 20 | 2 << 15 | (3 if f3 == 5 else 2) << 12 | (uimm & 31) << 7 | 0x27
    return None


def csr_read(m, a, trap):
    if a in (0x001, 0x002, 0x003):
        if fs(m) == 0:
            raise trap(2)
        return {0x001: m.fflags, 0x002: m.frm, 0x003: m.frm << 5 | m.fflags}[a]
    return None


def csr_write(m, a, v, trap):
    if a in (0x001, 0x002, 0x003):
        if fs(m) == 0:
            raise trap(2)
        if a == 0x001:
            m.fflags = v & 31
        elif a == 0x002:
            m.frm = v & 7
        else:
            m.fflags, m.frm = v & 31, v >> 5 & 7
        set_dirty(m)
        return True
    return False


def execute(m, w, illegal):
    """Executes one FP instruction (opcode 0x07, 0x27, 0x43, 0x47, 0x4B, 0x4F or 0x53); raises `illegal` for an illegal one."""
    if fs(m) == 0:
        raise illegal
    op, rd, f3, rs1, rs2, f7 = w & 0x7F, w >> 7 & 31, w >> 12 & 7, w >> 15 & 31, w >> 20 & 31, w >> 25
    x, f = m.x, m.f
    ires = 0
    if op == 0x07:
        if f3 not in (2, 3):
            raise illegal
        addr = (x[rs1] + sext(w >> 20, 12)) & M32
        if f3 == 3 and addr & 7:
            raise type(illegal)(4, addr)
        if f3 == 2:
            v = BOXED | m.load(addr, 4, False)
        else:
            lo = m.load(addr, 4, False)
            hi = m.load((addr + 4) & M32, 4, False)
            v = hi << 32 | lo
        f[rd] = v
        set_dirty(m)
        return
    if op == 0x27:
        if f3 not in (2, 3):
            raise illegal
        addr = (x[rs1] + sext(f7 << 5 | rd, 12)) & M32
        v = f[rs2]
        if f3 == 3 and addr & 7:
            raise type(illegal)(6, addr)
        if f3 == 2:
            m.store(addr, 4, v & M32)
        else:
            m.store(addr, 4, v & M32)
            m.store((addr + 4) & M32, 4, v >> 32)
        return
    fmt = f7 & 3
    if fmt > 1:
        raise illegal
    dbl = fmt
    if op in (0x43, 0x47, 0x4B, 0x4F):
        rm = m.frm if f3 == 7 else f3
        if rm > 4:
            raise illegal
        o = {0x43: 5, 0x47: 6, 0x4B: 7, 0x4F: 8}[op]
        fres, _, flags, _ = R.run(o, dbl, rm, f[rs1], f[rs2], f[f7 >> 2], 0)
        f[rd] = fres
        m.fflags |= flags
        set_dirty(m)
        return
    f5 = f7 >> 2
    a, b = f[rs1], f[rs2]

    def rmode():
        rm = m.frm if f3 == 7 else f3
        if rm > 4:
            raise illegal
        return rm

    if f5 in (0, 1, 2, 3):
        o = f5
        fres, _, flags, wr = R.run(o, dbl, rmode(), a, b, 0, 0)
    elif f5 == 0x0B:
        if rs2 != 0:
            raise illegal
        fres, _, flags, wr = R.run(4, dbl, rmode(), a, 0, 0, 0)
    elif f5 == 4:
        if f3 not in (0, 1, 2):
            raise illegal
        fres, _, flags, wr = R.run(9 + f3, dbl, 0, a, b, 0, 0)
    elif f5 == 5:
        if f3 not in (0, 1):
            raise illegal
        fres, ires, flags, wr = R.run(12 + f3, dbl, 0, a, b, 0, 0)
    elif f5 == 8:
        if fmt == 0 and rs2 == 1:
            fres, _, flags, wr = R.run(22, 0, rmode(), a, 0, 0, 0)
        elif fmt == 1 and rs2 == 0:
            fres, _, flags, wr = R.run(23, 0, rmode(), a, 0, 0, 0)
        else:
            raise illegal
    elif f5 == 0x14:
        if f3 not in (0, 1, 2):
            raise illegal
        fres, ires, flags, wr = R.run({2: 14, 1: 15, 0: 16}[f3], dbl, 0, a, b, 0, 0)
    elif f5 == 0x18:
        if rs2 not in (0, 1):
            raise illegal
        fres, ires, flags, wr = R.run(18 + rs2, dbl, rmode(), a, 0, 0, 0)
    elif f5 == 0x1A:
        if rs2 not in (0, 1):
            raise illegal
        fres, ires, flags, wr = R.run(20 + rs2, dbl, rmode(), 0, 0, 0, x[rs1])
    elif f5 == 0x1C:
        if f3 == 1 and rs2 == 0:
            fres, ires, flags, wr = R.run(17, dbl, 0, a, 0, 0, 0)
        elif f3 == 0 and rs2 == 0 and fmt == 0:
            fres, ires, flags, wr = R.run(24, 0, 0, a, 0, 0, 0)
        else:
            raise illegal
    elif f5 == 0x1E:
        if f3 == 0 and rs2 == 0 and fmt == 0:
            fres, ires, flags, wr = R.run(25, 0, 0, 0, 0, 0, x[rs1])
        else:
            raise illegal
    else:
        raise illegal
    if wr:
        f[rd] = fres
        set_dirty(m)
    else:
        m.wreg(rd, ires)
    if flags:
        m.fflags |= flags
        set_dirty(m)
