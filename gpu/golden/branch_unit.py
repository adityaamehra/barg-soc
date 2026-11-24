"""Golden model of the branch unit (block `branch_unit`). Combinational.

The warp follows its lowest-numbered active lane l. When tmask is 0 there is no active lane: next_pc = pc + 4, diverged = 0. link = pc + 4.
ctrl NONE: next_pc = pc + 4. BRANCH: pc + imm when taken bit l is 1, else pc + 4. JAL: pc + imm.
JALR: (a_l + imm) with bit 0 cleared. diverged = 1 when the active lanes do not all agree: BRANCH, their taken bits differ; JALR, their targets differ; 0 for JAL and
NONE (a branch on lane-dependent data, which the ISA forbids); it changes nothing else.
"""

M = 0xFFFFFFFF


def golden_branch_unit(ctrl, taken, tmask, pc, imm, a):
    lanes = [i for i in range(4) if tmask >> i & 1]
    if not lanes:
        return {"next_pc": (pc + 4) & M, "link": (pc + 4) & M, "diverged": 0}

    def nxt(i):
        if ctrl == 1:
            return (pc + imm if taken >> i & 1 else pc + 4) & M
        if ctrl == 2:
            return (pc + imm) & M
        if ctrl == 3:
            return ((a >> 32 * i & M) + imm) & M & ~1
        return (pc + 4) & M

    if ctrl == 1:
        diverged = len({taken >> i & 1 for i in lanes}) > 1                 # the active lanes' taken bits differ
    elif ctrl == 3:
        diverged = len({nxt(i) for i in lanes}) > 1                         # the lanes' jump targets differ
    else:
        diverged = False
    return {"next_pc": nxt(lanes[0]), "link": (pc + 4) & M, "diverged": int(diverged)}


def vectors(rng):
    """Directed vectors: every control kind with every thread mask (including 0), taken bits, and lane values of `a`."""
    out = []
    for _ in range(1500):
        out.append({"ctrl": rng.randrange(4), "taken": rng.randrange(16), "tmask": rng.randrange(16),
                    "pc": rng.getrandbits(32) & ~3, "imm": rng.choice((0, 4, 8, 0xFFFFFFFC, rng.getrandbits(32))),
                    "a": sum(rng.getrandbits(32) << 32 * i for i in range(4))})
    return out
