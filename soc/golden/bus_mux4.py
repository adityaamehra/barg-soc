"""Golden model of the four-core bus multiplexer (block `bus_mux4`). Combinational. Written by hand.

Each output is the matching input of the core whose grant<k> is 1 (0 when no grant is 1; grants are one-hot or all zero)."""

SIGNALS = (("addr", 32), ("store_data", 32), ("memtype", 3), ("memsrc", 2), ("valid", 1), ("xcpt", 1), ("memwrite", 1), ("kill", 1),
           ("dmem_we", 1), ("dmem_wdata", 32))
NAMES = [f"grant{k}" for k in range(4)] + [f"{n}{k}" for k in range(4) for n, _ in SIGNALS]


def golden_bus_mux4(grant0, grant1, grant2, grant3, addr0, addr1, addr2, addr3, store_data0, store_data1, store_data2, store_data3, memtype0, memtype1, memtype2, memtype3, memsrc0, memsrc1, memsrc2, memsrc3, valid0, valid1, valid2, valid3, xcpt0, xcpt1, xcpt2, xcpt3, memwrite0, memwrite1, memwrite2, memwrite3, kill0, kill1, kill2, kill3, dmem_we0, dmem_we1, dmem_we2, dmem_we3, dmem_wdata0, dmem_wdata1, dmem_wdata2, dmem_wdata3):
    i = locals()
    g = next((k for k in range(4) if i[f"grant{k}"] & 1), None)
    return {n: 0 if g is None else i[f"{n}{g}"] & ((1 << w) - 1) for n, w in SIGNALS}


def vectors(rng):
    out = []
    for _ in range(2000):
        g = rng.choice([None, 0, 1, 2, 3])
        v = {f"grant{k}": int(g == k) for k in range(4)}
        v.update({f"{n}{k}": rng.getrandbits(w) for k in range(4) for n, w in SIGNALS})
        out.append(v)
    return out
