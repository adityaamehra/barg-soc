# BARG SIMT GPU, v0: instruction set

Each thread runs **RV32IM** plus `Zicsr` reads; a warp of 4 threads (lanes) issues one instruction for all its active lanes.
The extensions below follow the semantics of Vortex (Tine et al., MICRO 2021) for `wspawn`, `tmc`, `split`, `join`, `bar`, and
of NVIDIA's PTX `vote.sync` and `shfl.sync` for `vote` and `shfl`; the tensor instructions are a 4-lane version of a warp-level
matrix multiply whose accumulator lives in the unit, as Blackwell's tensor memory (`tcgen05.mma`, `.ld`, `.st`) and Virgo's
accumulator memory do. **The encodings are this design's own** and are not binary
compatible with Vortex. `demos/simt-gpu/model/simt.py` implements exactly this page; where they differ, one of them is wrong.

## Encodings

All are R-type: `funct7[31:25] rs2[24:20] rs1[19:15] funct3[14:12] rd[11:7] opcode[6:0]`.

| Instruction | opcode | funct3 | funct7 | Operands |
|---|---|---|---|---|
| `tmc rs1` | `custom-0` 0x0B | 0 | 0 | rd = rs2 = 0 |
| `wspawn rs1, rs2` | 0x0B | 1 | 0 | rd = 0 |
| `split rs1` | 0x0B | 2 | 0 | rd = rs2 = 0 |
| `join` | 0x0B | 3 | 0 | rd = rs1 = rs2 = 0 |
| `bar rs1, rs2` | 0x0B | 4 | 0 | rd = 0 |
| `vote.any rd, rs1` / `vote.all` / `vote.ballot` | 0x0B | 5 | 0 / 1 / 2 | rs2 = 0 |
| `shfl.idx rd, rs1, rs2` / `.xor` / `.up` / `.down` | 0x0B | 6 | 0 / 1 / 2 / 3 | |
| `mma.i8 rs1, rs2` | `custom-1` 0x2B | 0 | 0 | rd = 0 |
| `mma.ld rd, rs1` | 0x2B | 1 | 0 | rs2 = 0 |
| `mma.st rs1, rs2` | 0x2B | 2 | 0 | rd = 0 |
| `mma.zero` | 0x2B | 3 | 0 | rd = rs1 = rs2 = 0 |

Any other funct3/funct7 under these opcodes is an illegal instruction.

## Semantics

*Warp-wide operand* below means: the value of that register in the lowest-numbered active lane.

- **`tmc rs1`**: the thread mask becomes the low 4 bits of the warp-wide `rs1`. A mask of 0 ends the warp (it becomes inactive
  and its divergence stack is cleared).
- **`wspawn rs1, rs2`**: warps 1 .. min(`rs1`, 4) - 1 that are inactive become active at PC = warp-wide `rs2` with only lane 0
  active. Their registers other than x0 are **undefined**. Warps already active are left alone.
- **`split rs1`**: each active lane's predicate is `rs1 != 0`. Let T = active lanes with a true predicate, F = the rest. If both
  are non-empty: push (current mask, fall-through), push (F, PC + 4), set the mask to T. Otherwise push (current mask,
  fall-through) only. Execution continues at PC + 4.
- **`join`**: pop (mask, pc). The thread mask becomes mask; continue at pc, or at PC + 4 for a fall-through entry. A `join`
  with an empty stack is an error. Stack depth: 8 entries per warp; a `split` that would exceed it is an error.
- **`bar rs1, rs2`**: barrier number = warp-wide `rs1` (0..3), expected warps = warp-wide `rs2`. The warp waits until that many
  warps have reached barrier `rs1`; then all of them continue. If every active warp waits and none can be released, the
  core stops with an error (deadlock).
- **`vote.any rd, rs1`**: every active lane gets 1 if any active lane has `rs1 != 0`, else 0. **`vote.all`**: 1 if all active
  lanes do. **`vote.ballot`**: the mask of active lanes with `rs1 != 0`. The result is the same in every active lane, so a
  branch on it is uniform.
- **`shfl.* rd, rs1, rs2`**: lane *l* gets `rs1` of a source lane *s* (read from every lane's register file before any write,
  whether or not lane *s* is active): `.idx` s = `rs2` mod 4; `.xor` s = (l xor `rs2`) mod 4; `.up` s = l - `rs2`, or l if that
  is below 0; `.down` s = l + `rs2`, or l if that is 4 or more. `rs2` is each lane's own value.
- **The tensor unit** keeps, for each warp, a 4 x 4 accumulator of 32-bit values (lane *i* owns row *i*). All four lanes must be
  active for every tensor instruction, and the fields marked 0 above must be 0; otherwise it is an error.
  - **`mma.i8 rs1, rs2`**: ACC += A x B, A and B signed 8-bit (32-bit wrapping sums). Lane *i*'s `rs1` holds row *i* of A
    (element *k* in bits 8k+7..8k); lane *j*'s `rs2` holds column *j* of B (element *k* in bits 8k+7..8k).
  - **`mma.ld rd, rs1`**: lane *i* gets ACC[*i*][`rs1` mod 4].
  - **`mma.st rs1, rs2`**: ACC[*i*][`rs2` mod 4] = lane *i*'s `rs1` (an initial C, or a bias).
  - **`mma.zero`**: ACC = 0. The accumulators are 0 after the host's start.
  Every tensor instruction reads at most two registers and writes at most one, like every other instruction.

## CSRs (read-only; any write is an error)

| Address | Name | Value |
|---|---|---|
| 0xCC0 | `tid` | lane number 0..3 |
| 0xCC1 | `wid` | warp number 0..3 |
| 0xCC2 | `cid` | core number |
| 0xCC3 | `tmask` | the warp's thread mask |
| 0xCC4 | `gtid` | (cid x warps + wid) x lanes + tid |
| 0xCC5 | `karg` | the kernel argument pointer the host wrote |
| 0xFC0, 0xFC1, 0xFC2 | `nt`, `nw`, `nc` | lanes per warp, warps per core, cores |
| 0xC00, 0xC80, 0xC02, 0xC82 | `cycle`, `cycleh`, `instret`, `instreth` | counters |

## Other rules

- **Branches and `jalr` must be uniform** across the active lanes; divergence goes through `split`/`join` (or a `vote`). If
  they are not, the hardware follows the lowest-numbered active lane (the model stops, in strict mode, to catch the bug).
- **Threads of one warp must not wait on each other** (no spin locks inside a warp): the pre-Volta SIMT-stack rule.
- **Stores from several lanes to one address** in one instruction: the highest-numbered lane's value is kept.
- **Memory map** (one core): instruction memory 0x0000_0000, 2 KB (fetch only); global memory 0x1000_0000, 8 KB; shared memory
  0x2000_0000, 4 KB in 4 banks interleaved by word. Misaligned accesses and accesses outside data memory are errors.
- **Memory contents are undefined until written.** A kernel must not read data the host or the kernel itself has not written (the model and
  the behavioural RTL start at zero, but SRAM macros do not).
- `fence` does nothing (no caches); `ecall`, `ebreak`, `mret` and the privileged CSRs do not exist (illegal).
- **Start and end**: the host loads the memories, writes the start PC and `karg`, and starts warp 0 with lane 0 active. The
  core reports "done" when no warp is active, or "error" with the PC and warp of the faulting instruction.
