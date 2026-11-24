"""Golden model of the instruction memory (block `imem`): 512 words of 32 bits, no reset, contents unknown until written.

Clocked. rdata shows the word raddr selected at the last rising edge, as it was before that edge's write (a read of the address
being written shows the old word). Before any word has been written there, or before the first edge, rdata is unknown (None).
At each edge: rdata_reg = memory[raddr]; then, when we is 1, memory[waddr] = wdata.
"""

M = 0xFFFFFFFF


def golden_imem(trace):
    mem, rdata, out = {}, None, []
    for step in trace:
        out.append({"rdata": rdata})
        rdata = mem.get(step["raddr"] & 511)
        if step["we"] & 1:
            mem[step["waddr"] & 511] = step["wdata"] & M
    return out
