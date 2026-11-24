"""Instruction-level model of the BARG SIMT GPU, v0.

This is the golden reference for whole kernels: it says what every architectural register and memory byte holds after a kernel,
not how many cycles it takes. It shares no code with any RTL, any block golden model or the compiler.

    gpu = Gpu(Config())                       # 1 core, 4 warps x 4 lanes, the v0 memory map
    gpu.write(0x0, code); gpu.write(0x1000_0000, data)
    gpu.launch(pc=0, karg=0x1000_0100)        # warp 0, lane 0 starts at pc (as the hardware does after the host's start)
    stats = gpu.run()                         # until no warp is active
    gpu.read(0x1000_0200, 64)

Execution model (each point is a rule the hardware must follow too):
  * One warp instruction per step. The scheduler is round robin over the warps that are active and not waiting at a barrier,
    starting after the warp that issued last. Results do not depend on the order unless the kernel races, which is its bug.
  * Each active lane executes the instruction on its own registers. Inactive lanes change nothing.
  * An ordinary branch or jump must agree across the active lanes. If it does not, the hardware follows the lowest-numbered
    active lane; the model counts it, and in strict mode (the default) stops with an error, because it is a kernel bug
    (divergence must go through split / join).
  * Several lanes storing to the same address in one instruction: the highest-numbered lane's value is kept.
  * A spawned warp's registers are undefined except x0; the model fills them with POISON so a kernel that relies on them fails.
"""

from __future__ import annotations

from dataclasses import dataclass, field

M32 = 0xFFFFFFFF
POISON = 0xDEADBEEF

# --------------------------------------------------------------------------- #
# Encodings (ISA.md)
# --------------------------------------------------------------------------- #

OP_CUSTOM0 = 0x0B          # SIMT control
OP_CUSTOM1 = 0x2B          # tensor
OP_CUSTOM2 = 0x5B          # graphics (gfx/): gfx.cfg and pix are modelled here
F3_GFX_CFG, F3_GFX_PIX = 0, 5
F3_RAST, F3_RAST_EDGE, F3_TEX, F3_ZTEST = 1, 3, 4, 6
TEX_BASE, TEX_W = 0x5000_0000, 32              # the 32 x 32 RGB565 texture
Z_BASE = 0x4004_0000                            # the depth memory's host window (G2d), write only


def expand565(p: int) -> tuple[int, int, int]:
    r5, g6, b5 = p >> 11 & 31, p >> 5 & 63, p & 31
    return r5 << 3 | r5 >> 2, g6 << 2 | g6 >> 4, b5 << 3 | b5 >> 2
SCREEN_W, SCREEN_H = 320, 240

F3_TMC, F3_WSPAWN, F3_SPLIT, F3_JOIN, F3_BAR, F3_VOTE, F3_SHFL = range(7)
VOTE_ANY, VOTE_ALL, VOTE_BALLOT = 0, 1, 2
SHFL_IDX, SHFL_XOR, SHFL_UP, SHFL_DOWN = 0, 1, 2, 3
F3_MMA_I8, F3_MMA_LD, F3_MMA_ST, F3_MMA_ZERO = 0, 1, 2, 3    # tensor: the warp's accumulator lives in the unit

CSR_TID, CSR_WID, CSR_CID, CSR_TMASK, CSR_GTID, CSR_KARG = 0xCC0, 0xCC1, 0xCC2, 0xCC3, 0xCC4, 0xCC5
CSR_NT, CSR_NW, CSR_NC = 0xFC0, 0xFC1, 0xFC2
CSR_CYCLE, CSR_INSTRET, CSR_CYCLEH, CSR_INSTRETH = 0xC00, 0xC02, 0xC80, 0xC82


class GpuError(Exception):
    """The kernel did something the hardware defines as an error (the hardware stops the core and sets an error status)."""

    def __init__(self, reason: str, warp: int | None = None, pc: int | None = None):
        where = "" if warp is None else f" (warp {warp}, pc 0x{pc:08x})"
        super().__init__(reason + where)
        self.reason, self.warp, self.pc = reason, warp, pc


@dataclass
class Region:
    name: str
    base: int
    size: int
    fetch: bool = False        # instructions may be fetched from it
    data: bool = True          # loads and stores may access it
    bytes_: bytearray = field(default=None, repr=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.bytes_ is None:
            self.bytes_ = bytearray(self.size)

    def holds(self, addr: int, n: int) -> bool:
        return self.base <= addr and addr + n <= self.base + self.size


def v0_regions() -> list[Region]:
    """The v0 memory map of one core."""
    return [
        Region("imem", 0x0000_0000, 2 * 1024, fetch=True, data=False),
        Region("global", 0x1000_0000, 8 * 1024),
        Region("shared", 0x2000_0000, 4 * 1024),
    ]


@dataclass
class Config:
    lanes: int = 4
    warps: int = 4
    core_id: int = 0
    cores: int = 1
    ipdom_depth: int = 8
    barriers: int = 4
    regions: list[Region] = field(default_factory=v0_regions)
    strict: bool = True        # stop on a divergent ordinary branch
    line_bytes: int = 16       # a global memory line (lanes x 4 bytes): one transaction serves one line
    shared_name: str = "shared"
    global_name: str = "global"
    scheduler: str = "rr"      # rr (Vortex), gto (greedy then oldest, Rogers et al.), gty (greedy then youngest, NVIDIA)
    timing: "Timing | None" = None   # None: functional only; a Timing: also estimate cycles (see Timing)


@dataclass
class Timing:
    """Assumed latencies of the v0 pipeline, for comparing design choices, not for predicting the chip.

    Issue to write-back is `alu` cycles (operand read, execute, write-back; there is no forwarding, so a dependent
    instruction of the same warp waits that long). A branch, jump or SIMT control instruction is resolved in execute: the
    warp's next instruction can issue `control` cycles later. The divider is one iterative unit shared by all lanes and
    warps. The memory unit serves one global line (or one shared-memory bank round) per cycle. The tensor unit takes `mma`
    cycles per instruction (one column of D per step) and is busy for them.
    """
    alu: int = 4
    mul: int = 5
    div: int = 34
    control: int = 3
    load: int = 6              # plus one cycle per extra line or bank round
    mma: int = 4
    one_in_flight: int = 0     # > 0: a warp issues again only this many cycles after its previous instruction (or when that
                               # instruction's result is ready, if later): the v0 pipeline, which has no scoreboard


@dataclass
class Warp:
    wid: int
    lanes: int
    pc: int = 0
    tmask: int = 0
    regs: list[list[int]] = field(default_factory=list)
    ipdom: list[tuple[int, int | None]] = field(default_factory=list)   # (mask, pc); pc None = fall-through entry
    waiting: int | None = None                                         # barrier id

    def fill(self, value: int) -> None:
        self.regs = [[0] + [value] * 31 for _ in range(self.lanes)]


@dataclass
class Stats:
    steps: int = 0                      # warp instructions issued (the model's "cycle")
    thread_instructions: int = 0        # sum over issued instructions of the active lanes
    per_warp: list[int] = field(default_factory=list)
    divergent_branches: int = 0
    splits: int = 0
    divergent_splits: int = 0
    barriers: int = 0
    mma: int = 0
    global_accesses: int = 0            # warp load/store instructions to global memory
    global_transactions: int = 0        # distinct lines they touched
    shared_accesses: int = 0
    shared_cycles: int = 0              # with bank conflicts serialised
    cycles: int = 0                     # with a Timing: the estimated cycle count
    idle_cycles: int = 0                # cycles in which no warp could issue


def _s32(v: int) -> int:
    v &= M32
    return v - (1 << 32) if v & 0x8000_0000 else v


def _s8(v: int) -> int:
    v &= 0xFF
    return v - 256 if v & 0x80 else v


def _sext(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


class Gpu:
    def __init__(self, config: Config | None = None):
        self.cfg = config or Config()
        if not 1 <= self.cfg.lanes <= 32 or not 1 <= self.cfg.warps <= 32:
            raise ValueError("lanes and warps must be 1..32")
        self.full = (1 << self.cfg.lanes) - 1
        self.warps = [Warp(w, self.cfg.lanes) for w in range(self.cfg.warps)]
        for w in self.warps:
            w.fill(POISON)
        self.karg = 0
        self.barrier_arrived: list[set[int]] = [set() for _ in range(self.cfg.barriers)]
        self.last = self.cfg.warps - 1
        self.stats = Stats(per_warp=[0] * self.cfg.warps)
        self.store_hooks: list = []     # f(addr, nbytes, value) after every store of a lane
        self.cycle = 0
        self.reg_ready = [[0] * 32 for _ in range(self.cfg.warps)]
        self.warp_ready = [0] * self.cfg.warps
        self.unit_free = {"div": 0, "lsu": 0, "tensor": 0}
        self.acc = [[[0] * 4 for _ in range(4)] for _ in range(self.cfg.warps)]
        self.frame = [0] * (SCREEN_W * SCREEN_H)     # video memory, RGB565, pixel y * 320 + x (not cleared by a launch)
        self.texture = [0] * (TEX_W * TEX_W)         # texture memory, RGB565, texel ty * 32 + tx (written by the host only)
        self.depth = [0] * (SCREEN_W * SCREEN_H)     # depth memory, 16 bits per pixel (G2d)
        self.scissor = [0, 0, SCREEN_W, SCREEN_H]    # gfx.cfg 0..3: x0, y0, x1, y1 (9 bits)
        self._rast_reset()

    # ------------------------------------------------------------------ host side
    def region(self, addr: int, n: int) -> Region | None:
        return next((r for r in self.cfg.regions if r.holds(addr, n)), None)

    def write(self, addr: int, data: bytes) -> None:
        if Z_BASE <= addr and addr + len(data) <= Z_BASE + 2 * SCREEN_W * SCREEN_H:   # the depth window (G2d), write only
            for k, byte in enumerate(data):
                p, hi = divmod(addr - Z_BASE + k, 2)
                self.depth[p] = self.depth[p] & (0x00FF if hi else 0xFF00) | byte << (8 * hi)
            return
        if TEX_BASE <= addr and addr + len(data) <= TEX_BASE + 2 * TEX_W * TEX_W:     # the texture window (G2c), write only
            for k, byte in enumerate(data):
                t, hi = divmod(addr - TEX_BASE + k, 2)
                self.texture[t] = self.texture[t] & (0x00FF if hi else 0xFF00) | byte << (8 * hi)
            return
        r = self.region(addr, len(data))
        if r is None:
            raise ValueError(f"host write 0x{addr:08x}+{len(data)} is outside every region")
        r.bytes_[addr - r.base: addr - r.base + len(data)] = data

    def read(self, addr: int, n: int) -> bytes:
        r = self.region(addr, n)
        if r is None:
            raise ValueError(f"host read 0x{addr:08x}+{n} is outside every region")
        return bytes(r.bytes_[addr - r.base: addr - r.base + n])

    def read_words(self, addr: int, count: int) -> list[int]:
        raw = self.read(addr, 4 * count)
        return [int.from_bytes(raw[4 * i: 4 * i + 4], "little") for i in range(count)]

    def launch(self, pc: int, karg: int = 0, tmask: int = 1) -> None:
        """What the host's start does: warp 0 becomes active at pc with lane 0 (or tmask) active; every other warp is idle."""
        self.karg = karg & M32
        for w in self.warps:
            w.pc, w.tmask, w.ipdom, w.waiting = 0, 0, [], None
            w.fill(POISON)
        w0 = self.warps[0]
        w0.pc, w0.tmask = pc & M32, tmask & self.full
        self.barrier_arrived = [set() for _ in range(self.cfg.barriers)]
        self.cycle = 0
        self.reg_ready = [[0] * 32 for _ in range(self.cfg.warps)]
        self.warp_ready = [0] * self.cfg.warps
        self.unit_free = {"div": 0, "lsu": 0, "tensor": 0}
        self.acc = [[[0] * 4 for _ in range(4)] for _ in range(self.cfg.warps)]
        self.scissor = [0, 0, SCREEN_W, SCREEN_H]
        self._rast_reset()

    def active(self) -> bool:
        return any(w.tmask for w in self.warps)

    def run(self, max_steps: int = 2_000_000) -> Stats:
        while self.active():
            if self.stats.steps >= max_steps:
                raise GpuError(f"no end after {max_steps} warp instructions")
            self.step()
        return self.stats

    # ------------------------------------------------------------------ scheduling
    def step(self) -> None:
        if self.cfg.timing is not None:
            self._timed_step()
            return
        n = self.cfg.warps
        for i in range(1, n + 1):
            w = self.warps[(self.last + i) % n]
            if w.tmask and w.waiting is None:
                self._issue(w)
                return
        self._deadlock()

    def _deadlock(self) -> None:
        waiting = [w.wid for w in self.warps if w.tmask]
        raise GpuError(f"deadlock: warps {waiting} all wait at a barrier that cannot be released")

    def _issue(self, w: Warp) -> None:
        self.last = w.wid
        self.stats.steps += 1
        self.stats.per_warp[w.wid] += 1
        self.stats.thread_instructions += bin(w.tmask).count("1")
        self.execute(w)

    def _pick(self, eligible: list[int]) -> int:
        policy, last, n = self.cfg.scheduler, self.last, self.cfg.warps
        if policy == "rr":
            return min(eligible, key=lambda wid: (wid - last - 1) % n)
        if policy in ("gto", "gty"):
            if last in eligible:
                return last
            return min(eligible) if policy == "gto" else max(eligible)
        raise ValueError(f"unknown scheduler {policy!r}")

    def _timed_step(self) -> None:
        t = self.cfg.timing
        while True:
            candidates = [w for w in self.warps if w.tmask and w.waiting is None]
            if not candidates:
                self._deadlock()
            eligible, wake = [], []
            for w in candidates:
                srcs, dsts, unit = deps(self.fetch(w))
                ready = max([self.warp_ready[w.wid]] + [self.reg_ready[w.wid][r] for r in srcs + dsts] +
                            [self.unit_free.get(unit, 0)])
                (eligible if ready <= self.cycle else wake).append(w.wid if ready <= self.cycle else ready)
            if eligible:
                break
            nxt = min(wake)
            self.stats.idle_cycles += nxt - self.cycle
            self.cycle = nxt
        w = self.warps[self._pick(eligible)]
        srcs, dsts, unit = deps(self.fetch(w))
        before = (self.stats.global_transactions, self.stats.shared_cycles)
        waiting_before = {x.wid for x in self.warps if x.waiting is not None}
        self._issue(w)
        now = self.cycle
        rounds = (self.stats.global_transactions - before[0]) + (self.stats.shared_cycles - before[1])
        latency = {"alu": t.alu, "mul": t.mul, "div": t.div, "lsu": t.load + max(rounds - 1, 0), "tensor": t.alu + 1,
                   "control": t.alu}[unit]
        for r in dsts:
            self.reg_ready[w.wid][r] = now + latency
        self.warp_ready[w.wid] = now + (t.control if unit == "control" or is_control(self.last_inst) else 1)
        if t.one_in_flight:
            self.warp_ready[w.wid] = now + max([t.one_in_flight] + [latency for _ in dsts])
        if unit == "div":
            self.unit_free["div"] = now + t.div
        elif unit == "lsu":
            self.unit_free["lsu"] = now + max(rounds, 1)
        elif unit == "tensor":
            self.unit_free["tensor"] = now + t.mma
        for x in self.warps:                       # warps a barrier just released continue after it resolves
            if x.wid in waiting_before and x.waiting is None:
                self.warp_ready[x.wid] = max(self.warp_ready[x.wid], now + t.control)
        self.cycle = now + 1
        self.stats.cycles = self.cycle

    # ------------------------------------------------------------------ memory, as the lanes see it
    def _data_region(self, w: Warp, addr: int, n: int) -> Region:
        if addr % n:
            raise GpuError(f"misaligned {n}-byte access at 0x{addr:08x}", w.wid, w.pc)
        r = self.region(addr, n)
        if r is None or not r.data:
            raise GpuError(f"data access 0x{addr:08x} is outside data memory", w.wid, w.pc)
        return r

    def _account(self, regions_addrs: list[tuple[Region, int]]) -> None:
        if not regions_addrs:
            return
        names = {r.name for r, _ in regions_addrs}
        for name in names:
            addrs = [a for r, a in regions_addrs if r.name == name]
            if name == self.cfg.global_name:
                self.stats.global_accesses += 1
                self.stats.global_transactions += len({a // self.cfg.line_bytes for a in addrs})
            elif name == self.cfg.shared_name:
                self.stats.shared_accesses += 1
                banks: dict[int, set[int]] = {}
                for a in addrs:
                    banks.setdefault((a >> 2) % self.cfg.lanes, set()).add(a >> 2)
                self.stats.shared_cycles += max(len(v) for v in banks.values())

    def _lanes(self, w: Warp) -> list[int]:
        return [i for i in range(self.cfg.lanes) if w.tmask >> i & 1]

    # ------------------------------------------------------------------ one warp instruction
    def fetch(self, w: Warp) -> int:
        r = self.region(w.pc, 4)
        if w.pc % 4 or r is None or not r.fetch:
            raise GpuError(f"instruction fetch from 0x{w.pc:08x}", w.wid, w.pc)
        o = w.pc - r.base
        return int.from_bytes(r.bytes_[o: o + 4], "little")

    def execute(self, w: Warp) -> None:
        inst = self.fetch(w)
        self.last_inst = inst
        op = inst & 0x7F
        rd, f3, rs1, rs2, f7 = inst >> 7 & 31, inst >> 12 & 7, inst >> 15 & 31, inst >> 20 & 31, inst >> 25
        lanes = self._lanes(w)
        R = w.regs
        pc = w.pc
        nxt = pc + 4 & M32

        def wr(lane: int, value: int) -> None:
            if rd:
                R[lane][rd] = value & M32

        if op == 0x37:                                     # LUI
            for l in lanes:
                wr(l, inst & 0xFFFFF000)
        elif op == 0x17:                                   # AUIPC
            for l in lanes:
                wr(l, pc + (inst & 0xFFFFF000))
        elif op == 0x6F:                                   # JAL
            imm = _sext((inst >> 31 & 1) << 20 | (inst >> 12 & 0xFF) << 12 | (inst >> 20 & 1) << 11 | (inst >> 21 & 0x3FF) << 1, 21)
            for l in lanes:
                wr(l, nxt)
            nxt = pc + imm & M32
        elif op == 0x67 and f3 == 0:                       # JALR
            imm = _sext(inst >> 20, 12)
            targets = [(R[l][rs1] + imm) & ~1 & M32 for l in lanes]
            for l in lanes:
                wr(l, nxt)
            nxt = self._uniform(w, targets, "jalr target")
        elif op == 0x63:                                   # branches
            imm = _sext((inst >> 31 & 1) << 12 | (inst >> 7 & 1) << 11 | (inst >> 25 & 0x3F) << 5 | (inst >> 8 & 0xF) << 1, 13)
            takens = [self._branch(f3, R[l][rs1], R[l][rs2], w) for l in lanes]
            if self._uniform(w, takens, "branch"):
                nxt = pc + imm & M32
        elif op == 0x03:                                   # loads
            imm = _sext(inst >> 20, 12)
            size = {0: 1, 1: 2, 2: 4, 4: 1, 5: 2}.get(f3)
            if size is None:
                raise GpuError("illegal load", w.wid, pc)
            touched, values = [], {}
            for l in lanes:
                a = R[l][rs1] + imm & M32
                r = self._data_region(w, a, size)
                v = int.from_bytes(r.bytes_[a - r.base: a - r.base + size], "little")
                if f3 in (0, 1):
                    v = _sext(v, 8 * size) & M32
                values[l] = v
                touched.append((r, a))
            for l, v in values.items():
                wr(l, v)
            self._account(touched)
        elif op == 0x23:                                   # stores
            imm = _sext((inst >> 25) << 5 | (inst >> 7 & 31), 12)
            size = {0: 1, 1: 2, 2: 4}.get(f3)
            if size is None:
                raise GpuError("illegal store", w.wid, pc)
            touched = []
            for l in lanes:                                # a faulting store changes nothing: check every lane first
                self._data_region(w, R[l][rs1] + imm & M32, size)
            for l in lanes:                                # lane order: the highest lane writes last and wins
                a = R[l][rs1] + imm & M32
                r = self._data_region(w, a, size)
                v = R[l][rs2] & ((1 << 8 * size) - 1)
                r.bytes_[a - r.base: a - r.base + size] = v.to_bytes(size, "little")
                touched.append((r, a))
                for hook in self.store_hooks:
                    hook(a, size, v)
            self._account(touched)
        elif op == 0x13:                                   # OP-IMM
            imm = _sext(inst >> 20, 12)
            for l in lanes:
                wr(l, self._alu_imm(f3, f7, R[l][rs1], imm, rs2, w))
        elif op == 0x33:                                   # OP (RV32I and M)
            for l in lanes:
                wr(l, self._alu(f3, f7, R[l][rs1], R[l][rs2], w))
        elif op == 0x0F:                                   # FENCE: memory is not cached; nothing to order
            pass
        elif op == 0x73:                                   # SYSTEM: CSR reads only
            if f3 in (1, 2, 3, 5, 6, 7):
                csr = inst >> 20
                writes = f3 in (1, 5) or rs1 != 0
                if writes:
                    raise GpuError(f"write to read-only CSR 0x{csr:03x}", w.wid, pc)
                for l in lanes:
                    wr(l, self._csr(w, l, csr))
            else:
                raise GpuError(f"illegal system instruction 0x{inst:08x}", w.wid, pc)
        elif op == OP_CUSTOM0:
            nxt = self._simt(w, inst, f3, f7, rd, rs1, rs2, lanes, nxt)
        elif op == OP_CUSTOM1 and f7 == 0 and f3 in (F3_MMA_I8, F3_MMA_LD, F3_MMA_ST, F3_MMA_ZERO):
            self._mma(w, f3, rd, rs1, rs2)
        elif op == OP_CUSTOM2 and f7 == 0 and rd == 0 and f3 in (F3_GFX_CFG, F3_GFX_PIX):
            self._gfx(w, f3, rs1, rs2, lanes)
        elif op == OP_CUSTOM2 and f7 == 0 and f3 in (F3_RAST, F3_RAST_EDGE, F3_TEX, F3_ZTEST):
            for l, v in self._rast(w, f3, rs1, rs2, lanes).items():
                if rd:
                    w.regs[l][rd] = v
        else:
            raise GpuError(f"illegal instruction 0x{inst:08x}", w.wid, pc)
        w.pc = nxt

    # ------------------------------------------------------------------ pieces
    def _uniform(self, w: Warp, values: list, what: str):
        first = values[0]
        if any(v != first for v in values[1:]):
            self.stats.divergent_branches += 1
            if self.cfg.strict:
                raise GpuError(f"divergent {what} without split/join: lanes disagree ({values})", w.wid, w.pc)
        return first

    @staticmethod
    def _branch(f3: int, a: int, b: int, w: Warp) -> bool:
        if f3 == 0:
            return a == b
        if f3 == 1:
            return a != b
        if f3 == 4:
            return _s32(a) < _s32(b)
        if f3 == 5:
            return _s32(a) >= _s32(b)
        if f3 == 6:
            return a < b
        if f3 == 7:
            return a >= b
        raise GpuError("illegal branch", w.wid, w.pc)

    @staticmethod
    def _alu_imm(f3: int, f7: int, a: int, imm: int, shamt: int, w: Warp) -> int:
        if f3 == 0:
            return a + imm
        if f3 == 2:
            return int(_s32(a) < imm)
        if f3 == 3:
            return int(a < (imm & M32))
        if f3 == 4:
            return a ^ imm
        if f3 == 6:
            return a | imm
        if f3 == 7:
            return a & imm
        if f3 == 1 and f7 == 0:
            return a << shamt
        if f3 == 5 and f7 == 0:
            return a >> shamt
        if f3 == 5 and f7 == 0x20:
            return _s32(a) >> shamt
        raise GpuError("illegal OP-IMM", w.wid, w.pc)

    @staticmethod
    def _alu(f3: int, f7: int, a: int, b: int, w: Warp) -> int:
        sa, sb, sh = _s32(a), _s32(b), b & 31
        if f7 == 0:
            return [a + b, a << sh, int(sa < sb), int(a < b), a ^ b, a >> sh, a | b, a & b][f3]
        if f7 == 0x20 and f3 == 0:
            return a - b
        if f7 == 0x20 and f3 == 5:
            return sa >> sh
        if f7 == 1:                                         # M extension
            if f3 == 0:
                return a * b
            if f3 == 1:
                return (sa * sb) >> 32
            if f3 == 2:
                return (sa * b) >> 32
            if f3 == 3:
                return (a * b) >> 32
            if f3 == 4:                                     # DIV
                if b == 0:
                    return M32
                if sa == -(1 << 31) and sb == -1:
                    return a
                q = abs(sa) // abs(sb)
                return q if (sa < 0) == (sb < 0) else -q
            if f3 == 5:                                     # DIVU
                return M32 if b == 0 else a // b
            if f3 == 6:                                     # REM
                if b == 0:
                    return a
                if sa == -(1 << 31) and sb == -1:
                    return 0
                r = abs(sa) % abs(sb)
                return r if sa >= 0 else -r
            if f3 == 7:                                     # REMU
                return a if b == 0 else a % b
        raise GpuError("illegal OP", w.wid, w.pc)

    def _csr(self, w: Warp, lane: int, csr: int) -> int:
        c = self.cfg
        table = {
            CSR_TID: lane, CSR_WID: w.wid, CSR_CID: c.core_id, CSR_TMASK: w.tmask,
            CSR_GTID: (c.core_id * c.warps + w.wid) * c.lanes + lane, CSR_KARG: self.karg,
            CSR_NT: c.lanes, CSR_NW: c.warps, CSR_NC: c.cores,
            CSR_CYCLE: self.stats.steps & M32, CSR_CYCLEH: self.stats.steps >> 32 & M32,
            CSR_INSTRET: self.stats.steps & M32, CSR_INSTRETH: self.stats.steps >> 32 & M32,
        }
        if csr not in table:
            raise GpuError(f"no CSR 0x{csr:03x}", w.wid, w.pc)
        return table[csr]

    def _first(self, w: Warp, reg: int) -> int:
        """A warp-wide operand (tmc, wspawn, bar): the value in the lowest-numbered active lane."""
        return w.regs[self._lanes(w)[0]][reg]

    def _simt(self, w: Warp, inst: int, f3: int, f7: int, rd: int, rs1: int, rs2: int, lanes: list[int], nxt: int) -> int:
        st = self.stats
        if f3 == F3_TMC and f7 == 0:
            w.tmask = self._first(w, rs1) & self.full
            if w.tmask == 0:
                w.ipdom = []
            return nxt
        if f3 == F3_WSPAWN and f7 == 0:
            count, target = self._first(w, rs1), self._first(w, rs2)
            for other in self.warps[1:min(count, self.cfg.warps)]:
                if other.tmask == 0:
                    other.pc, other.tmask, other.ipdom, other.waiting = target & M32, 1, [], None
                    other.fill(POISON)
            return nxt
        if f3 == F3_SPLIT and f7 == 0:
            st.splits += 1
            pred = sum(1 << l for l in lanes if w.regs[l][rs1] != 0)
            taken, other = w.tmask & pred, w.tmask & ~pred
            need = 2 if taken and other else 1
            if len(w.ipdom) + need > self.cfg.ipdom_depth:
                raise GpuError("IPDOM stack overflow", w.wid, w.pc)
            w.ipdom.append((w.tmask, None))
            if taken and other:
                st.divergent_splits += 1
                w.ipdom.append((other, nxt))
                w.tmask = taken
            return nxt
        if f3 == F3_JOIN and f7 == 0:
            if not w.ipdom:
                raise GpuError("join with an empty IPDOM stack", w.wid, w.pc)
            mask, at = w.ipdom.pop()
            w.tmask = mask
            return nxt if at is None else at
        if f3 == F3_BAR and f7 == 0:
            bid, count = self._first(w, rs1), self._first(w, rs2)
            if bid >= self.cfg.barriers:
                raise GpuError(f"no barrier {bid}", w.wid, w.pc)
            st.barriers += 1
            arrived = self.barrier_arrived[bid]
            arrived.add(w.wid)
            if len(arrived) >= count:
                for other in self.warps:
                    if other.waiting == bid:
                        other.waiting = None
                arrived.clear()
            else:
                w.waiting = bid
            return nxt
        if f3 == F3_VOTE and f7 in (VOTE_ANY, VOTE_ALL, VOTE_BALLOT):
            ballot = sum(1 << l for l in lanes if w.regs[l][rs1] != 0)
            value = {VOTE_ANY: int(ballot != 0), VOTE_ALL: int(ballot == w.tmask), VOTE_BALLOT: ballot}[f7]
            for l in lanes:
                if rd:
                    w.regs[l][rd] = value
            return nxt
        if f3 == F3_SHFL and f7 in (SHFL_IDX, SHFL_XOR, SHFL_UP, SHFL_DOWN):
            n = self.cfg.lanes
            src = [row[rs1] for row in w.regs]                         # every lane's register, read before any write
            out = {}
            for l in lanes:
                k = w.regs[l][rs2]
                if f7 == SHFL_IDX:
                    s = k % n
                elif f7 == SHFL_XOR:
                    s = (l ^ k) % n
                elif f7 == SHFL_UP:
                    s = l - k if 0 <= l - k else l
                else:
                    s = l + k if l + k < n else l
                out[l] = src[s]
            for l, v in out.items():
                if rd:
                    w.regs[l][rd] = v
            return nxt
        raise GpuError(f"illegal SIMT instruction 0x{inst:08x}", w.wid, w.pc)

    def _rast_reset(self) -> None:
        """The raster unit's state: box, edge coefficients, bias, and a scan per warp."""
        self.rbox = [0, 0, 0, 0]                        # gfx.cfg 8: x0 (bits 1:0 cleared), y0; 9: x1, y1 (inclusive, 9 bits)
        self.rcoef = [0] * 9                            # gfx.cfg 16..24: A0 B0 C0 A1 B1 C1 A2 B2 C2 (32 bits)
        self.rbias = 0                                  # gfx.cfg 25: bits 2:0, the top-left bias of edges 0..2
        self.tex_mode = 0                               # gfx.cfg 32: bit 0 bilinear, bit 1 u clamp, bit 2 v clamp
        self.blend = 0                                  # gfx.cfg 4: bit 0 source-over
        self.rscan = [[0, 0, 1] for _ in range(self.cfg.warps)]     # x, y, done

    def _edge(self, i: int, x: int, y: int) -> int:
        A, B, C = self.rcoef[3 * i: 3 * i + 3]
        return (A * x + B * y + C) & M32

    def _rast(self, w: Warp, f3: int, rs1: int, rs2: int, lanes: list[int]) -> dict[int, int]:
        """rast: lane l gets the position (y << 16) | x of pixel x = scan x + l of row scan y, with y replaced by 0xFFFF when the
        pixel is not covered (E_i + bias_i > 0, signed 32 bits, for the three edges); every lane gets 0xFFFFFFFF when the warp's
        scan is done. Then the warp's scan moves on by one group: x + 4, or past x1 back to x0 four rows down; past y1 it is done.
        rast.edge: lane l gets edge (rs2 bits 1:0) at the position rs1 (x = bits 15:0, y = bits 31:16), 0 for edge 3.
        tex, ztest: not yet built (G2c, G2d): rd = 0."""
        R, out = w.regs, {}
        if f3 == F3_RAST:
            sx, sy, done = self.rscan[w.wid]
            for l in lanes:
                if done:
                    out[l] = M32
                    continue
                x, y = (sx + l) & 0xFFFF, sy & 0xFFFF
                cov = all(_sext((self._edge(i, x, y) + (self.rbias >> i & 1)) & M32, 32) > 0 for i in range(3))
                out[l] = (y if cov else 0xFFFF) << 16 | x
            if lanes and not done:
                x0, _y0, x1, y1 = self.rbox
                if sx + 4 > x1:
                    sx, sy = x0, sy + 4
                    done = int(sy > y1)
                else:
                    sx += 4
                self.rscan[w.wid] = [sx, sy, done]
            return out
        for l in lanes:
            if f3 == F3_RAST_EDGE:
                i, pos = R[l][rs2] & 3, R[l][rs1]
                out[l] = 0 if i == 3 else self._edge(i, pos & 0xFFFF, pos >> 16)
            elif f3 == F3_TEX:
                out[l] = self._tex(R[l][rs1], R[l][rs2])
            else:
                out[l] = 0
        if f3 == F3_ZTEST:
            # per bank the highest-numbered lane on the screen is tested; it passes when z < the stored depth
            winner = {}
            for l in lanes:
                pos = R[l][rs1]
                x, y = pos & 0xFFFF, pos >> 16
                if x < SCREEN_W and y < SCREEN_H:
                    winner[x & 3] = (l, y * SCREEN_W + x)
            for l, p in winner.values():
                z = R[l][rs2] & 0xFFFF
                if z < self.depth[p]:
                    self.depth[p] = z
                    out[l] = M32
        return out

    def _tex(self, u: int, v: int) -> int:
        """tex: the texture at (u, v), unsigned 8.8 texels (bits 15:0), point or bilinear, repeat or clamp per axis; ARGB8888, alpha 0xFF."""
        m = self.tex_mode

        def wrap(c: int, clamp: int) -> int:
            return min(c, TEX_W - 1) if clamp else c % TEX_W
        iu, iv, fu, fv = u >> 8 & 255, v >> 8 & 255, u & 255, v & 255
        texel = lambda x, y: expand565(self.texture[y * TEX_W + x])      # noqa: E731
        if not m & 1:
            r, g, b = texel(wrap(iu, m & 2), wrap(iv, m & 4))
        else:
            x0, x1, y0, y1 = wrap(iu, m & 2), wrap(iu + 1, m & 2), wrap(iv, m & 4), wrap(iv + 1, m & 4)
            c = [texel(x0, y0), texel(x1, y0), texel(x0, y1), texel(x1, y1)]
            wt = [(256 - fu) * (256 - fv), fu * (256 - fv), (256 - fu) * fv, fu * fv]
            r, g, b = ((sum(wt[k] * c[k][ch] for k in range(4)) + 32768) >> 16 for ch in range(3))
        return 0xFF000000 | r << 16 | g << 8 | b

    def _gfx(self, w: Warp, f3: int, rs1: int, rs2: int, lanes: list[int]) -> None:
        """gfx.cfg: the lowest active lane's rs1 is the register number, its rs2 the value (registers 0..3, the scissor box x0,
        y0, x1, y1, 9 bits each; any other number is ignored). pix: every active lane writes colour rs2 (ARGB8888, alpha unused,
        truncated to RGB565) at pixel (rs1 bits 31:16 = y, 15:0 = x) when x < 320, y < 240 and the pixel is inside the scissor
        box (x0 <= x < x1, y0 <= y < y1). Two lanes on one video-memory bank (the same x mod 4): the highest-numbered lane's
        pixel is the one written, as stores to one address."""
        R = w.regs
        if f3 == F3_GFX_CFG:
            if lanes:
                reg, value = R[lanes[0]][rs1], R[lanes[0]][rs2]
                if reg < 4:
                    self.scissor[reg] = value & 0x1FF
                elif reg == 8:                          # the box's first corner; every warp's scan restarts
                    x0, y0 = value & 0x1FC, value >> 16 & 0x1FF
                    self.rbox[0], self.rbox[1] = x0, y0
                    for k in range(self.cfg.warps):
                        sy = y0 + ((k - y0) & 3)
                        self.rscan[k] = [x0, sy, int(sy > self.rbox[3] or x0 > self.rbox[2])]
                elif reg == 9:
                    self.rbox[2], self.rbox[3] = value & 0x1FF, value >> 16 & 0x1FF
                elif 16 <= reg <= 24:
                    self.rcoef[reg - 16] = value & M32
                elif reg == 25:
                    self.rbias = value & 7
                elif reg == 32:
                    self.tex_mode = value & 7
                elif reg == 4:
                    self.blend = value & 1
            return
        x0, y0, x1, y1 = self.scissor
        bank_winner = {}
        for l in lanes:
            pos, col = R[l][rs1], R[l][rs2]
            x, y = pos & 0xFFFF, pos >> 16
            if x < SCREEN_W and y < SCREEN_H and x0 <= x < x1 and y0 <= y < y1:
                bank_winner[x & 3] = (y * SCREEN_W + x, col)
        for p, col in bank_winner.values():
            if self.blend & 1:                          # source-over (G2c-2), the destination widened from RGB565
                a, d = col >> 24 & 255, expand565(self.frame[p])
                out = 0
                for k, sh in enumerate((16, 8, 0)):
                    x_ = (col >> sh & 255) * a + d[k] * (255 - a)
                    out |= ((x_ + 128 + ((x_ + 128) >> 8)) >> 8) << sh
                col = out
            v = rgb565(col)
            self.frame[p] = v

    def _mma(self, w: Warp, f3: int, rd: int, rs1: int, rs2: int) -> None:
        """The tensor unit. Each warp has a 4 x 4 accumulator of 32-bit values inside the unit (as Blackwell's tensor memory and
        Virgo's accumulator memory): mma.i8 adds A x B to it, mma.ld and mma.st move one column between it and a register,
        mma.zero clears it. Every lane must be active."""
        if self.cfg.lanes != 4:
            raise GpuError("the tensor instructions are defined for 4-lane warps", w.wid, w.pc)
        if w.tmask != self.full:
            raise GpuError("tensor instructions need every lane of the warp active", w.wid, w.pc)
        R, acc = w.regs, self.acc[w.wid]
        if f3 == F3_MMA_I8:
            if rd != 0:
                raise GpuError("mma.i8 has no destination register (rd must be x0)", w.wid, w.pc)
            a = [[_s8(R[i][rs1] >> 8 * k) for k in range(4)] for i in range(4)]       # lane i: row i of A
            b = [[_s8(R[j][rs2] >> 8 * k) for j in range(4)] for k in range(4)]       # lane j: column j of B
            for i in range(4):
                for j in range(4):
                    acc[i][j] = (acc[i][j] + sum(a[i][k] * b[k][j] for k in range(4))) & M32
            self.stats.mma += 1
        elif f3 == F3_MMA_LD:                                       # lane i: rd = acc[i][rs1 mod 4]
            values = [acc[i][R[i][rs1] & 3] for i in range(4)]
            for i in range(4):
                if rd:
                    R[i][rd] = values[i]
        elif f3 == F3_MMA_ST:                                       # lane i: acc[i][rs2 mod 4] = rs1
            if rd != 0:
                raise GpuError("mma.st has no destination register (rd must be x0)", w.wid, w.pc)
            for i in range(4):
                acc[i][R[i][rs2] & 3] = R[i][rs1] & M32
        else:                                                       # mma.zero
            if rd or rs1 or rs2:
                raise GpuError("mma.zero has no operands", w.wid, w.pc)
            for i in range(4):
                acc[i] = [0, 0, 0, 0]


# --------------------------------------------------------------------------- #
# What an instruction reads, writes and uses: for the timing estimate (the scoreboard and the unit busy times)
# --------------------------------------------------------------------------- #

def is_control(inst: int) -> bool:
    op = inst & 0x7F
    return op in (0x6F, 0x67, 0x63)


def rgb565(argb: int) -> int:
    """ARGB8888 to RGB565 by truncation: r >> 3, g >> 2, b >> 3 (alpha is dropped)."""
    return (argb >> 19 & 31) << 11 | (argb >> 10 & 63) << 5 | (argb >> 3 & 31)


def deps(inst: int) -> tuple[list[int], list[int], str]:
    """(source registers, destination registers, unit) of one instruction; x0 is never a dependence."""
    op = inst & 0x7F
    rd, f3, rs1, rs2, f7 = inst >> 7 & 31, inst >> 12 & 7, inst >> 15 & 31, inst >> 20 & 31, inst >> 25
    nz = lambda regs: [r for r in regs if r]
    if op in (0x37, 0x17):
        return [], nz([rd]), "alu"
    if op == 0x6F:
        return [], nz([rd]), "control"
    if op == 0x67:
        return nz([rs1]), nz([rd]), "control"
    if op == 0x63:
        return nz([rs1, rs2]), [], "control"
    if op == 0x03:
        return nz([rs1]), nz([rd]), "lsu"
    if op == 0x23:
        return nz([rs1, rs2]), [], "lsu"
    if op == 0x13:
        return nz([rs1]), nz([rd]), "alu"
    if op == 0x33:
        if f7 == 1:
            return nz([rs1, rs2]), nz([rd]), "mul" if f3 < 4 else "div"
        return nz([rs1, rs2]), nz([rd]), "alu"
    if op == 0x73:
        return [], nz([rd]), "alu"
    if op == OP_CUSTOM0:
        if f3 in (F3_VOTE, F3_SHFL):
            return nz([rs1, rs2] if f3 == F3_SHFL else [rs1]), nz([rd]), "alu"
        return nz([rs1, rs2]), [], "control"
    if op == OP_CUSTOM1:
        return nz([rs1, rs2]), nz([rd]), "tensor"
    if op == OP_CUSTOM2:
        return nz([rs1, rs2]), [], "alu"
    return [], [], "alu"
