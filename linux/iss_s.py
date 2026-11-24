"""A Python RV32IMAC simulator with M, S and U modes and Sv32 paging: the golden model of the core with an MMU.

    python3 demos/linux-soc/iss_s.py <image.bin> [--commands "uname,ls /,fork"] [--prompt "barg# "] [--max-instructions N]
                                     [--trace-file out.txt] [--log-csr] [--quiet]

Written by hand from the RISC-V privileged specification (1.12), not from any run. It executes a flat image from 0x8000_0000 on the
final SoC's memory map (64 MB RAM, CLINT, 16550 UART; the PLIC is absent: Linux polls the UART), with the devices of
demos/nuttx-soc/iss.py (the hand-written golden models of golden-sys/models). Booting OpenSBI + Linux to the shell on it checks
the software and this specification together, before any RTL runs; `--trace-file` gives the per-instruction trace to compare with
the RTL (pc, and the register written), and `--log-csr` lists every CSR the software touches and every trap it takes.

What the hardware does and does not do (the RTL is specified the same way):
  * CSRs: mstatus (MIE SIE MPIE SPIE SPP MPP MPRV SUM MXR TVM TW TSR), misa, medeleg, mideleg, mie, mip, mtvec, mcounteren, mscratch,
    mepc, mcause, mtval, mcycle(h), minstret(h), mvendorid, marchid, mimpid, mhartid; sstatus, sie, sip, stvec, scounteren, sscratch,
    sepc, scause, stval, satp; cycle(h), instret(h) (allowed by mcounteren/scounteren). No `time` CSR (OpenSBI emulates it), no PMP,
    no mstatush, no menvcfg: those read as illegal instructions, which OpenSBI probes for safely.
  * Sv32 with 4 MB megapages; no hardware A/D update (a page fault when A is 0, or D is 0 on a store); ASIDs ignored; sfence.vma
    flushes everything.
  * Interrupts: MEI, MSI, MTI, SEI, SSI, STI in that priority; SSIP, STIP, SEIP writable by M.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).parent
NUTTX = HERE.parent / "nuttx-soc"
M32 = 0xFFFFFFFF
RAM_BASE, RAM_SIZE = 0x80000000, 64 << 20


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rvc = _load(NUTTX / "rvc" / "rvc_golden.py", "rvc_golden")
fp = _load(HERE / "iss_fp.py", "iss_fp")   # the F and D extensions (a hart with them: misa, mstatus.FS, fflags/frm/fcsr, FP registers)
clint_m = _load(NUTTX / "golden-sys" / "models" / "clint_model.py", "g_clint")
uart_m = _load(NUTTX / "golden-sys" / "models" / "uart_model.py", "g_uart")


def sext(x: int, bits: int) -> int:
    return x - (1 << bits) if x >> (bits - 1) & 1 else x


def tdiv(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


class Trap(Exception):
    def __init__(self, cause: int, tval: int = 0):
        self.cause, self.tval = cause, tval & M32


U, S, M = 0, 1, 3
FETCH, LOAD, STORE = 0, 1, 2
PF = {FETCH: 12, LOAD: 13, STORE: 15}
AF = {FETCH: 1, LOAD: 5, STORE: 7}
# mstatus bits
MIE, SIE, MPIE, SPIE, SPP, MPRV, SUM, MXR, TVM, TW, TSR = 3, 1, 7, 5, 8, 17, 18, 19, 20, 21, 22
MSTATUS_MASK = (1 << SIE | 1 << MIE | 1 << SPIE | 1 << MPIE | 1 << SPP | 3 << 11 | 1 << MPRV | 1 << SUM | 1 << MXR | 1 << TVM
                | 1 << TW | 1 << TSR | 3 << 13)
SSTATUS_MASK = 1 << SIE | 1 << SPIE | 1 << SPP | 1 << SUM | 1 << MXR | 3 << 13
MEDELEG_MASK = 0xB3FF          # causes 0-9, 12, 13, 15 (not 11, ecall from M)
MIDELEG_MASK = 0x222           # SSI, STI, SEI
MIP_M_WRITABLE = 0x222         # SSIP, STIP, SEIP
SIP_S_WRITABLE = 0x002         # SSIP
MISA = 0x40000000 | 1 << 0 | 1 << 2 | 1 << 3 | 1 << 5 | 1 << 8 | 1 << 12 | 1 << 18 | 1 << 20   # RV32 A C D F I M S U


class Machine:
    def __init__(self, image: bytes, hartid: int = 0):
        self.ram = bytearray(RAM_SIZE)
        self.ram[:len(image)] = image
        self.x = [0] * 32
        self.f = [0] * 32                                   # FP registers (64 bits; a single is NaN-boxed)
        self.fflags = self.frm = 0
        self.pc = RAM_BASE
        self.priv = M
        self.hartid = hartid
        self.mstatus = 3 << 11 if False else 0
        self.medeleg = self.mideleg = self.mie = self.mip_sw = 0
        self.mtvec = self.mscratch = self.mepc = self.mcause = self.mtval = self.mcounteren = 0
        self.stvec = self.sscratch = self.sepc = self.scause = self.stval = self.scounteren = self.satp = 0
        self.mcycle = self.minstret = 0
        self.resv = None
        self.tlb: dict[tuple[int, int], tuple[int, int]] = {}
        self.clint, self.uart = clint_m.Clint(), uart_m.Uart()
        reset = {"rst": 1, "addr": 0, "wdata": 0, "we": 0, "re": 0, "rx_valid": 0, "rx_data": 0}
        self.clint.edge(reset)
        self.uart.edge(reset)
        self.out = bytearray()
        self.last_write = None
        self.csr_log: dict[str, int] = {}
        self.trap_log: dict[str, int] = {}
        self.log = False

    # ------------------------------------------------------------ devices and physical memory
    def mip(self) -> int:
        c = self.clint.s
        return self.mip_sw | (int(c["time"] >= c["cmp"]) << 7) | (c["msip"] << 3)

    def _uart_rx_ready(self) -> bool:
        return not self.uart.s["dr"]

    def pload(self, pa: int, size: int, kind: int, va: int) -> int:
        if pa >> 26 == RAM_BASE >> 26:
            off = pa - RAM_BASE
            return int.from_bytes(self.ram[off:off + size], "little")
        if kind == FETCH:
            raise Trap(AF[kind], va)
        if pa >> 16 == 0x0200:                      # word registers: a narrower load takes its bytes of the word
            v = self.clint.outputs({"addr": pa, "wdata": 0, "we": 0})["rdata"]
            return (v >> 8 * (pa & 3)) & ((1 << 8 * size) - 1)
        if pa >> 12 == 0x10000:                     # one byte per register, in bits 7:0 whatever the offset
            probe = {"addr": pa, "wdata": 0, "we": 0, "re": 1, "rx_valid": 0, "rx_data": 0}
            v = self.uart.outputs(probe)["rdata"]
            self.uart.edge({"rst": 0, **probe})
            return v & ((1 << 8 * size) - 1)
        raise Trap(AF[kind], va)

    def pstore(self, pa: int, size: int, value: int, va: int) -> None:
        value &= (1 << 8 * size) - 1
        if pa >> 26 == RAM_BASE >> 26:
            off = pa - RAM_BASE
            self.ram[off:off + size] = value.to_bytes(size, "little")
            if self.resv is not None and self.resv >> 2 == pa >> 2:
                pass                                # own store does not clear (only another hart's would)
            return
        if pa >> 16 == 0x0200:
            if size != 4:
                raise Trap(7, va)
            self.clint.edge({"rst": 0, "addr": pa, "wdata": value, "we": 1})
            return
        if pa >> 12 == 0x10000:
            if (pa & 7) == 0 and not (self.uart.s["lcr"] >> 7 & 1):
                self.out.append(value & 0xFF)
            self.uart.edge({"rst": 0, "addr": pa, "wdata": value & 0xFF, "we": 1, "re": 0, "rx_valid": 0, "rx_data": 0})
            return
        raise Trap(7, va)

    # ------------------------------------------------------------ Sv32
    def translate(self, va: int, kind: int) -> int:
        priv = self.priv
        if kind != FETCH and self.mstatus >> MPRV & 1 and priv == M:
            priv = self.mstatus >> 11 & 3
        if priv == M or not self.satp >> 31:
            return va
        key = (va >> 12, kind * 4 + priv * 16 + (self.mstatus >> SUM & 1) * 64 + (self.mstatus >> MXR & 1) * 128)
        hit = self.tlb.get(key)
        if hit is not None:
            return hit | (va & 0xFFF)
        a = (self.satp & 0x3FFFFF) << 12
        level = 1
        while True:
            vpn = va >> 22 if level == 1 else va >> 12 & 0x3FF
            pte_addr = a + vpn * 4
            if pte_addr >> 26 != RAM_BASE >> 26:
                raise Trap(AF[kind], va)
            off = pte_addr - RAM_BASE
            pte = int.from_bytes(self.ram[off:off + 4], "little")
            v, r, w, x, u, ad = pte & 1, pte >> 1 & 1, pte >> 2 & 1, pte >> 3 & 1, pte >> 4 & 1, pte >> 6 & 3
            if not v or (not r and w):
                raise Trap(PF[kind], va)
            if r or x:
                break
            if level == 0:
                raise Trap(PF[kind], va)
            a = (pte >> 10 & 0x3FFFFF) << 12
            level = 0
        ppn = pte >> 10 & 0x3FFFFF
        if level == 1 and ppn & 0x3FF:
            raise Trap(PF[kind], va)                # misaligned megapage
        if priv == U and not u:
            raise Trap(PF[kind], va)
        if priv == S and u and (kind == FETCH or not self.mstatus >> SUM & 1):
            raise Trap(PF[kind], va)
        ok = x if kind == FETCH else (r or (x and self.mstatus >> MXR & 1)) if kind == LOAD else w
        if not ok or not ad & 1 or (kind == STORE and not ad >> 1 & 1):
            raise Trap(PF[kind], va)
        if level == 1:
            pa_page = (ppn >> 10) << 22 | (va & 0x3FF000)
        else:
            pa_page = ppn << 12
        if pa_page >> 32:
            raise Trap(AF[kind], va)
        self.tlb[key] = pa_page
        return pa_page | (va & 0xFFF)

    def load(self, va: int, size: int, signed: bool) -> int:
        va &= M32
        if va & (size - 1):
            raise Trap(4, va)
        v = self.pload(self.translate(va, LOAD), size, LOAD, va)
        return sext(v, 8 * size) & M32 if signed else v

    def store(self, va: int, size: int, value: int) -> None:
        va &= M32
        if va & (size - 1):
            raise Trap(6, va)
        self.pstore(self.translate(va, STORE), size, value, va)

    def fetch16(self, va: int) -> int:
        pa = self.translate(va, FETCH)
        return self.pload(pa, 2, FETCH, va)

    # ------------------------------------------------------------ CSRs
    def _counter_ok(self, a: int) -> bool:
        bit = a & 31
        if self.priv == M:
            return True
        if not self.mcounteren >> bit & 1:
            return False
        return self.priv == S or bool(self.scounteren >> bit & 1)

    def csr_read(self, a: int) -> int:
        if self.log:
            self.csr_log[f"r {a:03x}"] = self.csr_log.get(f"r {a:03x}", 0) + 1
        if (a >> 8 & 3) > self.priv:
            raise Trap(2)
        if a == 0x180 and self.priv == S and self.mstatus >> TVM & 1:
            raise Trap(2)
        if a in (0xC00, 0xC02, 0xC80, 0xC82):
            if not self._counter_ok(a):
                raise Trap(2)
            return {0xC00: self.mcycle & M32, 0xC02: self.minstret & M32, 0xC80: self.mcycle >> 32 & M32,
                    0xC82: self.minstret >> 32 & M32}[a]
        v = fp.csr_read(self, a, Trap)
        if v is not None:
            return v
        mip = self.mip()
        sd = (1 << 31) if (self.mstatus >> 13 & 3) == 3 else 0     # SD: the FP state is dirty
        table = {0x300: self.mstatus | sd, 0x301: MISA, 0x302: self.medeleg, 0x303: self.mideleg, 0x304: self.mie, 0x305: self.mtvec,
                 0x306: self.mcounteren, 0x340: self.mscratch, 0x341: self.mepc, 0x342: self.mcause, 0x343: self.mtval, 0x344: mip,
                 0xB00: self.mcycle & M32, 0xB80: self.mcycle >> 32 & M32, 0xB02: self.minstret & M32, 0xB82: self.minstret >> 32 & M32,
                 0xF11: 0, 0xF12: 0, 0xF13: 0, 0xF14: self.hartid,
                 0x100: (self.mstatus & SSTATUS_MASK) | sd, 0x104: self.mie & self.mideleg, 0x105: self.stvec, 0x106: self.scounteren,
                 0x140: self.sscratch, 0x141: self.sepc, 0x142: self.scause, 0x143: self.stval, 0x144: mip & self.mideleg,
                 0x180: self.satp}
        if a not in table:
            raise Trap(2)
        return table[a]

    def csr_write(self, a: int, v: int) -> None:
        if self.log:
            self.csr_log[f"w {a:03x}"] = self.csr_log.get(f"w {a:03x}", 0) + 1
        v &= M32
        if a >> 10 == 3 or (a >> 8 & 3) > self.priv:
            raise Trap(2)
        if fp.csr_write(self, a, v, Trap):
            return
        if a == 0x300:
            mpp = v >> 11 & 3
            v = (v & ~(3 << 11)) | ((mpp if mpp != 2 else self.mstatus >> 11 & 3) << 11)
            self.mstatus = v & MSTATUS_MASK
        elif a == 0x302:
            self.medeleg = v & MEDELEG_MASK
        elif a == 0x303:
            self.mideleg = v & MIDELEG_MASK
        elif a == 0x304:
            self.mie = v & 0xAAA
        elif a == 0x305:
            self.mtvec = v & ~2
        elif a == 0x306:
            self.mcounteren = v & 7
        elif a == 0x340:
            self.mscratch = v
        elif a == 0x341:
            self.mepc = v & ~1
        elif a == 0x342:
            self.mcause = v
        elif a == 0x343:
            self.mtval = v
        elif a == 0x344:
            self.mip_sw = v & MIP_M_WRITABLE
        elif a in (0x301, 0xB00, 0xB80, 0xB02, 0xB82):
            pass
        elif a == 0x100:
            self.mstatus = (self.mstatus & ~SSTATUS_MASK) | (v & SSTATUS_MASK)
        elif a == 0x104:
            self.mie = (self.mie & ~self.mideleg) | (v & self.mideleg & 0x222)
        elif a == 0x105:
            self.stvec = v & ~2
        elif a == 0x106:
            self.scounteren = v & 7
        elif a == 0x140:
            self.sscratch = v
        elif a == 0x141:
            self.sepc = v & ~1
        elif a == 0x142:
            self.scause = v
        elif a == 0x143:
            self.stval = v
        elif a == 0x144:
            self.mip_sw = (self.mip_sw & ~(self.mideleg & SIP_S_WRITABLE)) | (v & self.mideleg & SIP_S_WRITABLE)
        elif a == 0x180:
            if self.priv == S and self.mstatus >> TVM & 1:
                raise Trap(2)
            self.satp = v & 0x803FFFFF
            self.tlb.clear()
        else:
            raise Trap(2)
        if a in (0x300, 0x100):
            self.tlb.clear()

    # ------------------------------------------------------------ traps
    def take_trap(self, cause: int, tval: int, interrupt: bool) -> None:
        if getattr(self, "trap_trace", None) is not None:  # --trap-trace FILE: "<e|i><cause> <pc> <tval> <from priv>" for every trap
            self.trap_trace.write(f"{'i' if interrupt else 'e'}{cause} {self.pc & ~1:x} {tval:x} {'USxM'[self.priv]}\n")
        if self.log:
            k = f"{'irq' if interrupt else 'exc'} {cause} from {'USxM'[self.priv]}"
            self.trap_log[k] = self.trap_log.get(k, 0) + 1
        deleg = (self.mideleg if interrupt else self.medeleg) >> cause & 1
        self.resv = None
        if deleg and self.priv <= S:
            self.sepc, self.scause, self.stval = self.pc & ~1, cause | (1 << 31 if interrupt else 0), tval
            st = self.mstatus
            st = (st & ~(1 << SPIE)) | ((st >> SIE & 1) << SPIE)
            st = (st & ~(1 << SIE) & ~(1 << SPP)) | (self.priv << SPP)
            self.mstatus = st
            self.priv = S
            base = self.stvec & ~3
            self.pc = base + 4 * cause if interrupt and self.stvec & 1 else base
        else:
            self.mepc, self.mcause, self.mtval = self.pc & ~1, cause | (1 << 31 if interrupt else 0), tval
            st = self.mstatus
            st = (st & ~(1 << MPIE)) | ((st >> MIE & 1) << MPIE)
            st = (st & ~(1 << MIE) & ~(3 << 11)) | (self.priv << 11)
            self.mstatus = st
            self.priv = M
            base = self.mtvec & ~3
            self.pc = base + 4 * cause if interrupt and self.mtvec & 1 else base
        self.tlb.clear()

    def pending_interrupt(self) -> int | None:
        p = self.mip() & self.mie
        if not p:
            return None
        for cause in (11, 3, 7, 9, 1, 5):
            if not p >> cause & 1:
                continue
            if self.mideleg >> cause & 1:
                if self.priv < S or (self.priv == S and self.mstatus >> SIE & 1):
                    return cause
            elif self.priv < M or self.mstatus >> MIE & 1:
                return cause
        return None

    # ------------------------------------------------------------ the run
    def wreg(self, rd: int, v: int) -> None:
        if rd:
            self.x[rd] = v & M32
            self.last_write = (rd, v & M32)

    def step(self) -> None:
        self.last_write = None
        self.retired = False
        c = self.clint.s
        c["time"] = (c["time"] + 1) & 0xFFFFFFFFFFFFFFFF
        self.mcycle += 1
        irq = self.pending_interrupt()
        if irq is not None:
            self.take_trap(irq, 0, True)
            return
        try:
            pc = self.pc
            if pc & 1:
                raise Trap(0, pc)
            half = self.fetch16(pc)
            if half & 3 != 3:
                fpw = fp.fp_expand(half)
                illegal, word = (False, fpw) if fpw is not None else rvc.expand(half)
                if illegal:
                    raise Trap(2, half)
                length = 2
            else:
                word = half | self.fetch16((pc + 2) & M32) << 16
                length = 4
            self.execute(word, length)
            self.retired = True
            self.minstret += 1
        except Trap as t:
            self.take_trap(t.cause, t.tval, False)

    def execute(self, w: int, length: int) -> None:
        x = self.x
        op, rd, f3, rs1, rs2, f7 = w & 0x7F, w >> 7 & 31, w >> 12 & 7, w >> 15 & 31, w >> 20 & 31, w >> 25
        next_pc = (self.pc + length) & M32
        a, b = x[rs1], x[rs2]
        sa, sb = sext(a, 32), sext(b, 32)
        illegal = Trap(2, w)
        if op == 0x37:
            self.wreg(rd, w & 0xFFFFF000)
        elif op == 0x17:
            self.wreg(rd, self.pc + sext(w & 0xFFFFF000, 32))
        elif op == 0x6F:
            imm = sext(((w >> 31) << 20) | (w >> 12 & 0xFF) << 12 | (w >> 20 & 1) << 11 | (w >> 21 & 0x3FF) << 1, 21)
            self.wreg(rd, next_pc)
            next_pc = (self.pc + imm) & M32
        elif op == 0x67 and f3 == 0:
            target = (a + sext(w >> 20, 12)) & M32 & ~1
            self.wreg(rd, next_pc)
            next_pc = target
        elif op == 0x63:
            imm = sext(((w >> 31) << 12) | (w >> 7 & 1) << 11 | (w >> 25 & 0x3F) << 5 | (w >> 8 & 0xF) << 1, 13)
            taken = {0: a == b, 1: a != b, 4: sa < sb, 5: sa >= sb, 6: a < b, 7: a >= b}.get(f3)
            if taken is None:
                raise illegal
            if taken:
                next_pc = (self.pc + imm) & M32
        elif op == 0x03:
            size, signed = {0: (1, True), 1: (2, True), 2: (4, False), 4: (1, False), 5: (2, False)}.get(f3, (0, False))
            if not size:
                raise illegal
            self.wreg(rd, self.load(a + sext(w >> 20, 12), size, signed))
        elif op == 0x23:
            size = {0: 1, 1: 2, 2: 4}.get(f3)
            if size is None:
                raise illegal
            self.store(a + sext(f7 << 5 | rd, 12), size, b)
        elif op == 0x13:
            imm = sext(w >> 20, 12)
            sh = w >> 20 & 31
            if f3 == 0:
                r = a + imm
            elif f3 == 2:
                r = int(sa < imm)
            elif f3 == 3:
                r = int(a < imm & M32)
            elif f3 == 4:
                r = a ^ imm
            elif f3 == 6:
                r = a | imm
            elif f3 == 7:
                r = a & imm
            elif f3 == 1 and f7 == 0:
                r = a << sh
            elif f3 == 5 and f7 == 0:
                r = a >> sh
            elif f3 == 5 and f7 == 0x20:
                r = sa >> sh
            else:
                raise illegal
            self.wreg(rd, r)
        elif op == 0x33:
            if f7 == 1:
                if f3 == 0:
                    r = sa * sb
                elif f3 == 1:
                    r = (sa * sb) >> 32
                elif f3 == 2:
                    r = (sa * b) >> 32
                elif f3 == 3:
                    r = (a * b) >> 32
                elif f3 == 4:
                    r = -1 if b == 0 else (sa if sa == -(1 << 31) and sb == -1 else tdiv(sa, sb))
                elif f3 == 5:
                    r = M32 if b == 0 else a // b
                elif f3 == 6:
                    r = sa if b == 0 else 0 if (sa == -(1 << 31) and sb == -1) else sa - sb * tdiv(sa, sb)
                else:
                    r = a if b == 0 else a % b
            elif f7 == 0 or (f7 == 0x20 and f3 in (0, 5)):
                if f3 == 0:
                    r = a - b if f7 else a + b
                elif f3 == 1:
                    r = a << (b & 31)
                elif f3 == 2:
                    r = int(sa < sb)
                elif f3 == 3:
                    r = int(a < b)
                elif f3 == 4:
                    r = a ^ b
                elif f3 == 5:
                    r = sa >> (b & 31) if f7 else a >> (b & 31)
                elif f3 == 6:
                    r = a | b
                else:
                    r = a & b
            else:
                raise illegal
            self.wreg(rd, r)
        elif op == 0x0F:
            if f3 == 1:
                pass                                # fence.i: one memory, nothing to do
            elif f3 != 0:
                raise illegal
        elif op == 0x73:
            if f3 == 0:
                if w == 0x00000073:
                    raise Trap(8 + self.priv)       # ecall from U (8), S (9), M (11)
                if w == 0x00100073:
                    raise Trap(3, self.pc)
                if w == 0x30200073:                 # mret
                    if self.priv < M:
                        raise illegal
                    st, mpp = self.mstatus, self.mstatus >> 11 & 3
                    st = (st & ~(1 << MIE)) | ((st >> MPIE & 1) << MIE) | 1 << MPIE
                    st &= ~(3 << 11)
                    if mpp != M:
                        st &= ~(1 << MPRV)
                    self.mstatus, self.priv = st, mpp
                    next_pc = self.mepc
                    self.tlb.clear()
                elif w == 0x10200073:               # sret
                    if self.priv < S or (self.priv == S and self.mstatus >> TSR & 1):
                        raise illegal
                    st, spp = self.mstatus, self.mstatus >> SPP & 1
                    st = (st & ~(1 << SIE)) | ((st >> SPIE & 1) << SIE) | 1 << SPIE
                    st &= ~(1 << SPP)
                    st &= ~(1 << MPRV)
                    self.mstatus, self.priv = st, spp
                    next_pc = self.sepc
                    self.tlb.clear()
                elif w == 0x10500073:               # wfi
                    if self.priv == U or (self.priv == S and self.mstatus >> TW & 1):
                        raise illegal
                    self.wfi()
                elif f7 == 0x09 and rd == 0:        # sfence.vma
                    if self.priv == U or (self.priv == S and self.mstatus >> TVM & 1):
                        raise illegal
                    self.tlb.clear()
                else:
                    raise illegal
            elif f3 == 4:
                raise illegal
            else:
                csr, src = w >> 20, (rs1 if f3 & 4 else a)
                writes = (f3 & 3 == 1) or rs1 != 0
                if writes and csr >> 10 == 3:
                    raise illegal
                if f3 & 3 == 1 and rd == 0:
                    old = 0
                    if (csr >> 8 & 3) > self.priv:
                        raise illegal
                else:
                    try:
                        old = self.csr_read(csr)
                    except Trap:
                        raise illegal from None
                new = src if f3 & 3 == 1 else old | src if f3 & 3 == 2 else old & ~src
                if writes:
                    try:
                        self.csr_write(csr, new)
                    except Trap:
                        raise illegal from None
                self.wreg(rd, old)
        elif op == 0x2F and f3 == 2:
            self.atomic(w, rd, a, b, sb)
        elif op in (0x07, 0x27, 0x43, 0x47, 0x4B, 0x4F, 0x53):
            fp.execute(self, w, illegal)
        else:
            raise illegal
        self.pc = next_pc

    def atomic(self, w: int, rd: int, a: int, b: int, sb: int) -> None:
        funct5 = w >> 27
        if funct5 == 2:                             # lr.w
            if w >> 20 & 31:
                raise Trap(2, w)
            if a & 3:
                raise Trap(4, a)
            pa = self.translate(a, LOAD)
            self.wreg(rd, self.pload(pa, 4, LOAD, a))
            self.resv = pa
            return
        if a & 3:
            raise Trap(6, a)
        pa = self.translate(a, STORE)
        if funct5 == 3:                             # sc.w
            ok = self.resv is not None and self.resv >> 2 == pa >> 2
            self.resv = None
            if ok:
                self.pstore(pa, 4, b, a)
            self.wreg(rd, 0 if ok else 1)
            return
        old = self.pload(pa, 4, STORE, a)
        so = sext(old, 32)
        new = {1: b, 0: old + b, 4: old ^ b, 12: old & b, 8: old | b, 16: min(so, sb), 20: max(so, sb),
               24: min(old, b), 28: max(old, b)}.get(funct5)
        if new is None:
            raise Trap(2, w)
        self.pstore(pa, 4, new & M32, a)
        self.wreg(rd, old)

    def wfi(self) -> None:
        c = self.clint.s
        if c["time"] < c["cmp"] < (1 << 64) - 1 and not (self.mip() & self.mie):
            c["time"] = c["cmp"]


def main() -> int:
    args = sys.argv[1:]
    image = Path(args[0]).read_bytes()
    opt = {a: args[i + 1] for i, a in enumerate(args) if a in ("--commands", "--prompt", "--max-instructions", "--trace-file", "--trap-trace")}
    commands = [c for c in opt.get("--commands", "").split(",") if c]
    prompt = opt.get("--prompt", "barg# ").encode()
    limit = int(opt.get("--max-instructions", 300_000_000))
    m = Machine(image)
    m.log = "--log-csr" in args
    m.trap_trace = open(opt["--trap-trace"], "w") if "--trap-trace" in opt else None
    m.x[10], m.x[11] = 0, 0                         # a0 = hart id, a1 = no FDT: OpenSBI uses the one built in
    trace = open(opt["--trace-file"], "w") if "--trace-file" in opt else None
    quiet = "--quiet" in args
    script = [(prompt, (c + "\r").encode()) for c in commands] + [(prompt, b"")]
    step_i, queue, scan_from, seen, n = 0, bytearray(), 0, 0, 0
    while n < limit:
        pc = m.pc
        m.step()
        n += 1
        if trace is not None and m.retired:
            wr = m.last_write
            trace.write(f"{pc:08x}" + (f" x{wr[0]}={wr[1]:08x}" if wr else "") + "\n")
        if len(m.out) > seen:
            if not quiet:
                sys.stdout.write(m.out[seen:].decode("latin-1"))
                sys.stdout.flush()
            seen = len(m.out)
            if step_i < len(script) and bytes(m.out[scan_from:]).endswith(script[step_i][0]):
                queue += script[step_i][1]
                step_i += 1
                scan_from = len(m.out)
                if step_i == len(script):
                    break
        if queue and n % 2000 == 0 and m._uart_rx_ready():
            m.uart.edge({"rst": 0, "addr": 0, "wdata": 0, "we": 0, "re": 0, "rx_valid": 1, "rx_data": queue.pop(0)})
    if trace is not None:
        trace.close()
    ok = step_i >= len(script)
    print(f"\n--- {'prompt reached after the last command' if ok else 'STOPPED before the end of the script'}; {n} instructions, "
          f"mtime {m.clint.s['time']}, pc {m.pc:08x}, priv {'USxM'[m.priv]}")
    if m.log:
        print("CSRs:", " ".join(f"{k}:{v}" for k, v in sorted(m.csr_log.items())))
        print("traps:", " ".join(f"[{k}]:{v}" for k, v in sorted(m.trap_log.items())))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
