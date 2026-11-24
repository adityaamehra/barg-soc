"""Golden model of lane 1's register file (block `regfile1`): 128 words of 32 bits, two asynchronous read ports, one write
port, no reset, contents unknown until written.

Clocked. rdata and rdata2 show the words raddr and raddr2 select, at once, as they are before the cycle's edge (a read of the
address being written shows the old word); unknown (None) for a word never written. At each edge, when we is 1,
memory[waddr] = wdata.
"""

M = 0xFFFFFFFF


def golden_regfile1(trace):
    mem, out = {}, []
    for step in trace:
        out.append({"rdata": mem.get(step["raddr"] & 127), "rdata2": mem.get(step["raddr2"] & 127)})
        if step["we"] & 1:
            mem[step["waddr"] & 127] = step["wdata"] & M
    return out
