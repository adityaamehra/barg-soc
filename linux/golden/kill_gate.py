"""Golden model of `kill_gate` (two kills): regwrite is cancelled by kill_wb (a trap or mret being taken, which kills the instruction
in write-back too); memwrite is cancelled by kill_mem (any redirect, including a CSR refetch, which kills the younger instructions).
Combinational. Written by hand."""


def golden_kill_gate(regwrite, memwrite, kill_wb, kill_mem):
    return {"regwrite_out": int(bool(regwrite & 1) and not (kill_wb & 1)),
            "memwrite_out": int(bool(memwrite & 1) and not (kill_mem & 1))}


def vectors(rng):
    return [{"regwrite": a, "memwrite": b, "kill_wb": c, "kill_mem": d} for a in range(2) for b in range(2) for c in range(2) for d in range(2)] * 50
