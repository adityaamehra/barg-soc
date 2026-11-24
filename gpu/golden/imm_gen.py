"""A golden model of the demo's immediate generator, for checking benchmark results.

Written by hand from the block's description and the immsel encoding table, not from any run.
NO_IMMEDIATE (101) and the two reserved codes drive zero.
"""

M = 0xFFFFFFFF


def _extend(value, bits):
    """Sign-extend a `bits`-wide value to 32 bits."""
    return (value - (1 << bits) if value >> (bits - 1) & 1 else value) & M


def golden_imm_gen(inst, immsel):
    inst &= M
    bit = lambda n: (inst >> n) & 1                      # noqa: E731
    field = lambda hi, lo: (inst >> lo) & ((1 << (hi - lo + 1)) - 1)   # noqa: E731
    if immsel == 0:                                      # IMM_I
        imm = _extend(field(31, 20), 12)
    elif immsel == 1:                                    # IMM_S
        imm = _extend((field(31, 25) << 5) | field(11, 7), 12)
    elif immsel == 2:                                    # IMM_B
        imm = _extend((bit(31) << 12) | (bit(7) << 11) | (field(30, 25) << 5)
                      | (field(11, 8) << 1), 13)
    elif immsel == 3:                                    # IMM_U
        imm = field(31, 12) << 12
    elif immsel == 4:                                    # IMM_J
        imm = _extend((bit(31) << 20) | (field(19, 12) << 12) | (bit(20) << 11)
                      | (field(30, 21) << 1), 21)
    else:                                                # NO_IMMEDIATE and reserved
        imm = 0
    return {"imm": imm & M}
