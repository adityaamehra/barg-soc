"""Golden model of the cycle counter (block `cycle_ctr`): a 48-bit counter, synchronous reset, counting while enable is 1.

Clocked. count shows the counter's value; unknown (None) before the first reset. At each rising edge: rst sets it to 0;
otherwise when enable is 1 it goes up by one, wrapping to 0 after 2**48 - 1.
"""


def golden_cycle_ctr(trace):
    count, out = None, []
    for step in trace:
        out.append({"count": count})
        if step["rst"] & 1:
            count = 0
        elif count is not None and step["enable"] & 1:
            count = (count + 1) % (1 << 48)
    return out
