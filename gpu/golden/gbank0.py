"""Golden model of global memory bank 0 (block `gbank0`): 512 words of 32 bits with a write enable per byte, one address
for the read and the write, a synchronous read, no reset, contents unknown until written.

Clocked. rdata shows the word addr selected at the last rising edge, as it was before that edge's write; a byte never written is
unknown, and a word with an unknown byte reads as unknown (None). At each edge: rdata_reg = memory[addr]; then each byte of
memory[addr] whose be bit is 1 and while we is 1 takes the same byte of wdata.
"""

DEPTH = 512


def golden_gbank0(trace):
    mem, rdata, out = {}, None, []
    for step in trace:
        out.append({"rdata": rdata})
        a = step["addr"] % DEPTH
        word = mem.get(a, [None] * 4)
        rdata = None if any(b is None for b in word) else sum(b << 8 * i for i, b in enumerate(word))
        if step["we"] & 1:
            new = list(word)
            for i in range(4):
                if step["be"] >> i & 1:
                    new[i] = step["wdata"] >> 8 * i & 0xFF
            mem[a] = new
    return out
