"""Tests of the GPU model against ISA.md, with hand-assembled programs; the expected values are computed here, independently.

    ./.venv-harness/bin/python -m pytest demos/simt-gpu/model -q
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import simt  # noqa: E402
from asm import Asm  # noqa: E402

G = 0x1000_0000      # global memory
S = 0x2000_0000      # shared memory
M32 = 0xFFFFFFFF


def run(a: Asm, *, karg=0, data: dict[int, bytes] | None = None, cfg: simt.Config | None = None, max_steps=200_000):
    gpu = simt.Gpu(cfg or simt.Config())
    gpu.write(0, a.assemble())
    for addr, raw in (data or {}).items():
        gpu.write(addr, raw)
    gpu.launch(0, karg)
    gpu.run(max_steps)
    return gpu


def prologue(a: Asm, warps: int = 1) -> None:
    """Spawn `warps` warps at 'body', turn on every lane, end each warp with tmc 0 at 'end'."""
    a.li("t0", warps)
    a.la("t1", "body")
    a.wspawn("t0", "t1")
    a.label("body")
    a.li("t0", 0xF)
    a.tmc("t0")


def epilogue(a: Asm) -> None:
    a.label("end")
    a.tmc("zero")


def store_gtid_slot(a: Asm, value_reg: str) -> None:
    """global[gtid] = value_reg (clobbers t5, t6)."""
    a.csrr("t5", "gtid")
    a.slli("t5", "t5", 2)
    a.li("t6", G)
    a.add("t5", "t5", "t6")
    a.sw(value_reg, 0, "t5")


def test_each_lane_computes_on_its_own_registers():
    a = Asm()
    prologue(a, warps=4)
    a.csrr("s0", "gtid")              # 0..15
    a.li("s1", -7)
    a.mul("s2", "s0", "s1")           # gtid * -7
    a.addi("s2", "s2", 100)
    a.li("s3", 3)
    a.div("s4", "s2", "s3")           # (100 - 7 gtid) / 3, rounding toward zero
    store_gtid_slot(a, "s4")
    epilogue(a)
    gpu = run(a)
    got = [simt._s32(v) for v in gpu.read_words(G, 16)]
    want = [int((100 - 7 * g) / 3) for g in range(16)]
    assert got == want
    w = gpu.stats.per_warp                    # every warp ran the body; warp 0 also the 4-instruction spawn (li, la, wspawn)
    assert w[1:] == [w[1]] * 3 and w[0] == w[1] + 4


def test_ids_and_counts():
    a = Asm()
    prologue(a, warps=4)
    a.csrr("s0", "tid"); a.csrr("s1", "wid"); a.csrr("s2", "nt"); a.csrr("s3", "nw")
    a.slli("s1", "s1", 8); a.slli("s2", "s2", 16); a.slli("s3", "s3", 24)
    a.or_("s0", "s0", "s1"); a.or_("s0", "s0", "s2"); a.or_("s0", "s0", "s3")
    store_gtid_slot(a, "s0")
    epilogue(a)
    got = run(a).read_words(G, 16)
    assert got == [4 << 24 | 4 << 16 | (g // 4) << 8 | g % 4 for g in range(16)]


def test_split_join_runs_both_paths_and_restores_the_mask():
    # x = tid even ? 10 + tid : 20 + tid, then, nested inside the odd path: tid == 3 adds 100.
    a = Asm()
    prologue(a)
    a.csrr("s0", "tid")
    a.andi("s1", "s0", 1)
    a.xori("s1", "s1", 1)                 # s1 = (tid even)
    a.split("s1")
    a.beqz("s1", "else")
    a.addi("s2", "s0", 10)
    a.j("join")
    a.label("else")
    a.addi("s2", "s0", 20)
    a.addi("s3", "s0", -3)
    a.sltiu("s3", "s3", 1)                # s3 = (tid == 3)
    a.split("s3")
    a.beqz("s3", "inner_join")
    a.addi("s2", "s2", 100)
    a.label("inner_join")
    a.join()
    a.label("join")
    a.join()
    a.csrr("s4", "tmask")                 # all lanes again
    a.slli("s4", "s4", 16)
    a.or_("s2", "s2", "s4")
    store_gtid_slot(a, "s2")
    epilogue(a)
    gpu = run(a)
    assert gpu.read_words(G, 4) == [0xF << 16 | v for v in (10, 21, 12, 123)]
    assert gpu.stats.divergent_splits == 2
    assert gpu.warps[0].ipdom == []


def test_a_uniform_split_pushes_one_entry_and_takes_one_path():
    a = Asm()
    prologue(a)
    a.li("s1", 1)
    a.split("s1")
    a.beqz("s1", "else")
    a.li("s2", 5)
    a.j("join")
    a.label("else")
    a.li("s2", 9)
    a.label("join")
    a.join()
    store_gtid_slot(a, "s2")
    epilogue(a)
    gpu = run(a)
    assert gpu.read_words(G, 4) == [5] * 4
    assert gpu.stats.divergent_splits == 0


def test_a_divergent_branch_without_split_is_an_error_in_strict_mode_and_follows_lane0_otherwise():
    a = Asm()
    prologue(a)
    a.csrr("s0", "tid")
    a.li("s2", 1)
    a.bnez("s0", "skip")                  # lanes disagree
    a.li("s2", 2)
    a.label("skip")
    store_gtid_slot(a, "s2")
    epilogue(a)
    with pytest.raises(simt.GpuError, match="divergent branch"):
        run(a)
    gpu = run(a, cfg=simt.Config(strict=False))
    assert gpu.read_words(G, 4) == [2] * 4    # lane 0 does not branch, so nobody does
    assert gpu.stats.divergent_branches == 1


def test_a_data_dependent_loop_with_vote_and_split():
    # Each lane sums 1..(tid + 1): a loop whose trip count differs per lane, written the only way SIMT allows.
    a = Asm()
    prologue(a)
    a.csrr("s0", "tid")
    a.addi("s0", "s0", 1)                 # n = tid + 1
    a.li("s1", 0)                          # i
    a.li("s2", 0)                          # sum
    a.label("loop")
    a.slt("t0", "s1", "s0")               # p = i < n
    a.vote(simt.VOTE_ANY, "t1", "t0")
    a.beqz("t1", "done")                  # uniform: nobody has work left
    a.split("t0")
    a.beqz("t0", "skip")
    a.addi("s1", "s1", 1)
    a.add("s2", "s2", "s1")
    a.label("skip")
    a.join()
    a.j("loop")
    a.label("done")
    store_gtid_slot(a, "s2")
    epilogue(a)
    assert run(a).read_words(G, 4) == [1, 3, 6, 10]


def test_vote_ballot_and_all():
    a = Asm()
    prologue(a)
    a.csrr("s0", "tid")
    a.sltiu("s1", "s0", 2)                # tid < 2
    a.vote(simt.VOTE_BALLOT, "s2", "s1")
    a.vote(simt.VOTE_ALL, "s3", "s1")
    a.li("s4", 1)
    a.vote(simt.VOTE_ALL, "s5", "s4")
    a.slli("s3", "s3", 8); a.slli("s5", "s5", 16)
    a.or_("s2", "s2", "s3"); a.or_("s2", "s2", "s5")
    store_gtid_slot(a, "s2")
    epilogue(a)
    assert run(a).read_words(G, 4) == [0b0011 | 0 << 8 | 1 << 16] * 4


def test_shfl_xor_butterfly_reduction():
    a = Asm()
    prologue(a)
    a.csrr("s0", "tid")
    a.addi("s0", "s0", 1)
    a.mul("s0", "s0", "s0")               # values 1, 4, 9, 16
    for k in (1, 2):
        a.li("t0", k)
        a.shfl(simt.SHFL_XOR, "t1", "s0", "t0")
        a.add("s0", "s0", "t1")
    store_gtid_slot(a, "s0")
    epilogue(a)
    assert run(a).read_words(G, 4) == [30] * 4


@pytest.mark.parametrize("mode,shift,want", [
    (simt.SHFL_IDX, 2, [12, 12, 12, 12]), (simt.SHFL_UP, 1, [10, 10, 11, 12]), (simt.SHFL_DOWN, 1, [11, 12, 13, 13])])
def test_shfl_modes(mode, shift, want):
    a = Asm()
    prologue(a)
    a.csrr("s0", "tid")
    a.addi("s0", "s0", 10)
    a.li("t0", shift)
    a.shfl(mode, "s1", "s0", "t0")
    store_gtid_slot(a, "s1")
    epilogue(a)
    assert run(a).read_words(G, 4) == want


def test_mma_accumulates_a_times_b_onto_c_in_the_warps_accumulator():
    rnd = random.Random(7)
    A = [[rnd.randint(-128, 127) for _ in range(4)] for _ in range(4)]
    B = [[rnd.randint(-128, 127) for _ in range(4)] for _ in range(4)]
    B2 = [[rnd.randint(-128, 127) for _ in range(4)] for _ in range(4)]
    C = [[rnd.randint(-(1 << 31), (1 << 31) - 1) for _ in range(4)] for _ in range(4)]
    pack = lambda xs: sum((x & 0xFF) << 8 * k for k, x in enumerate(xs))
    data = bytearray()
    data += b"".join(pack(A[i]).to_bytes(4, "little") for i in range(4))                       # G + 0: rows of A
    data += b"".join(pack([B[k][j] for k in range(4)]).to_bytes(4, "little") for j in range(4))  # G + 16: columns of B
    data += b"".join(pack([B2[k][j] for k in range(4)]).to_bytes(4, "little") for j in range(4)) # G + 32: columns of B2
    data += b"".join((C[i][j] & M32).to_bytes(4, "little") for i in range(4) for j in range(4))  # G + 48: rows of C
    a = Asm()
    prologue(a)
    a.csrr("s0", "tid")
    a.li("t0", G)
    a.slli("s1", "s0", 2)
    a.add("s1", "s1", "t0")
    a.slli("s2", "s0", 4)
    a.add("s2", "s2", "t0")
    a.mma_zero()
    for j in range(4):                    # acc = C, one column at a time
        a.lw("t1", 48 + 4 * j, "s2")
        a.li("t2", j)
        a.mma_st("t1", "t2")
    a.lw("a0", 0, "s1")
    a.lw("a1", 16, "s1")
    a.lw("a2", 32, "s1")
    a.mma("a0", "a1")                     # acc += A x B
    a.mma("a0", "a2")                     # acc += A x B2
    a.li("t0", G + 0x100)
    a.add("s3", "s2", "t0")
    a.li("t0", G)
    a.sub("s3", "s3", "t0")               # s3 = G + 0x100 + 16 * tid
    for j in range(4):
        a.li("t2", j)
        a.mma_ld("t1", "t2")
        a.sw("t1", 4 * j, "s3")
    epilogue(a)
    gpu = run(a, data={G: bytes(data)})
    got = [[simt._s32(v) for v in gpu.read_words(G + 0x100 + 16 * i, 4)] for i in range(4)]
    want = [[simt._s32(C[i][j] + sum(A[i][k] * (B[k][j] + B2[k][j]) for k in range(4))) for j in range(4)] for i in range(4)]
    assert got == want
    assert gpu.stats.mma == 2


def test_each_warp_has_its_own_accumulator():
    a = Asm()
    prologue(a, warps=2)
    a.mma_zero()
    a.csrr("s0", "wid")
    a.addi("s0", "s0", 7)
    a.li("t2", 1)
    a.mma_st("s0", "t2")                  # column 1 = wid + 7 in every lane
    a.li("t1", 0)
    a.li("t2", 0)
    a.bar("t1", "t2")                      # a barrier of 0 warps never waits: a no-op that lets the other warp run
    a.li("t2", 1)
    a.mma_ld("s1", "t2")
    store_gtid_slot(a, "s1")
    epilogue(a)
    assert run(a).read_words(G, 8) == [7] * 4 + [8] * 4


def test_tensor_instructions_need_every_lane_and_no_stray_operands():
    a = Asm()
    a.mma("a0", "a1")                     # lane 0 only
    with pytest.raises(simt.GpuError, match="every lane"):
        run(a)
    a = Asm()
    prologue(a)
    a.raw(asm_enc(simt.OP_CUSTOM1, 5, simt.F3_MMA_I8, 10, 11))
    with pytest.raises(simt.GpuError, match="rd must be x0"):
        run(a)


def asm_enc(op, rd, f3, rs1, rs2, f7=0):
    return f7 << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | rd << 7 | op


def test_barrier_and_shared_memory_between_warps():
    # Each warp writes its 4 values to shared memory, waits at barrier 0, then reads the next warp's values.
    a = Asm()
    prologue(a, warps=4)
    a.csrr("s0", "gtid")
    a.li("t0", S)
    a.slli("s1", "s0", 2)
    a.add("s1", "s1", "t0")
    a.addi("s2", "s0", 1000)
    a.sw("s2", 0, "s1")
    a.li("t1", 0)
    a.li("t2", 4)
    a.bar("t1", "t2")
    a.addi("s3", "s0", 4)
    a.andi("s3", "s3", 15)                # the same lane of the next warp
    a.slli("s3", "s3", 2)
    a.add("s3", "s3", "t0")
    a.lw("s4", 0, "s3")
    store_gtid_slot(a, "s4")
    epilogue(a)
    gpu = run(a)
    assert gpu.read_words(G, 16) == [1000 + (g + 4) % 16 for g in range(16)]
    assert gpu.stats.barriers == 4
    assert gpu.stats.shared_cycles == gpu.stats.shared_accesses     # one word per bank: no conflict


def test_shared_bank_conflicts_and_global_coalescing_are_counted():
    a = Asm()
    prologue(a)
    a.csrr("s0", "tid")
    a.slli("s1", "s0", 4)                 # stride 16 bytes: every lane in bank 0
    a.li("t0", S)
    a.add("s1", "s1", "t0")
    a.sw("s0", 0, "s1")
    a.slli("s2", "s0", 2)                 # unit stride in global: one 16-byte line
    a.li("t0", G)
    a.add("s2", "s2", "t0")
    a.sw("s0", 0, "s2")
    a.slli("s3", "s0", 6)                 # stride 64: four lines
    a.add("s3", "s3", "t0")
    a.sw("s0", 64, "s3")
    epilogue(a)
    st = run(a).stats
    assert st.shared_cycles == 4
    assert st.global_transactions == 1 + 4


def test_a_barrier_that_can_never_be_released_is_a_deadlock():
    a = Asm()
    prologue(a, warps=2)
    a.li("t1", 0)
    a.li("t2", 3)                          # 3 warps expected, 2 exist
    a.bar("t1", "t2")
    epilogue(a)
    with pytest.raises(simt.GpuError, match="deadlock"):
        run(a)


@pytest.mark.parametrize("build,match", [
    (lambda a: a.join(), "empty IPDOM"),
    (lambda a: (a.li("t0", 0x1000_0002), a.lw("t1", 0, "t0")), "misaligned"),
    (lambda a: (a.li("t0", 0x3000_0000), a.sw("t1", 0, "t0")), "outside data memory"),
    (lambda a: a.lw("t1", 0, "zero"), "outside data memory"),           # instruction memory is not data
    (lambda a: a.raw(0xC0001073), "read-only CSR"),                      # unimp = csrrw x0, cycle, x0
    (lambda a: a.raw(0x00000073), "illegal system"),                     # ecall
    (lambda a: a.raw(0x0000700B), "illegal SIMT"),                       # custom-0, funct3 7
])
def test_errors(build, match):
    a = Asm()
    build(a)
    with pytest.raises(simt.GpuError, match=match):
        run(a)


def test_spawned_warps_start_with_poisoned_registers_and_lane_0():
    a = Asm()
    a.li("t0", 2)
    a.la("t1", "w1")
    a.wspawn("t0", "t1")
    a.tmc("zero")                          # warp 0 ends
    a.label("w1")
    a.csrr("s0", "tmask")
    a.li("t0", G)
    a.sw("s0", 0, "t0")
    a.sw("s5", 4, "t0")                    # never written: poison
    a.tmc("zero")
    gpu = run(a)
    assert gpu.read_words(G, 2) == [1, simt.POISON]


def test_the_timing_estimate_waits_for_a_dependence_and_hides_it_with_other_warps():
    def chain(warps):
        a = Asm()
        prologue(a, warps=warps)
        for _ in range(8):
            a.addi("s0", "s0", 1)                 # each depends on the one before
        epilogue(a)
        gpu = simt.Gpu(simt.Config(warps=warps, timing=simt.Timing(alu=4)))
        gpu.write(0, a.assemble())
        gpu.launch(0)
        return gpu.run()
    one, four = chain(1), chain(4)
    assert one.idle_cycles >= 7 * 3                # 3 bubbles between dependent instructions of one warp
    assert four.cycles < 4 * one.cycles            # four warps fill each other's bubbles
    assert four.idle_cycles < one.idle_cycles * 4


def test_a_faulting_store_changes_nothing():
    # Lane 0's address is fine, lane 1's is misaligned: the instruction faults as a whole, so lane 0's word stays 0
    # (the RTL's load-store unit behaves this way; fuzz_rtl.py found the model writing lane 0 first).
    a = Asm()
    prologue(a)
    a.csrr("s0", "tid")
    a.li("s2", G)
    a.slli("s3", "s0", 6)
    a.add("s2", "s2", "s3")
    a.addi("s4", "s0", -1)
    a.sltiu("s4", "s4", 1)               # 1 in lane 1 only
    a.add("s2", "s2", "s4")
    a.li("s5", 0x55)
    a.sw("s5", 0, "s2")
    epilogue(a)
    gpu = simt.Gpu(simt.Config())
    gpu.write(0, a.assemble())
    gpu.launch(0)
    with pytest.raises(simt.GpuError, match="misaligned"):
        gpu.run()
    assert gpu.read_words(G, 1) == [0]
