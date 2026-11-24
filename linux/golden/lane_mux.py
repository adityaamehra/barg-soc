"""Golden model of `lane_mux`: a core's lane on the shared bus, taken by its page-table walker while that walks. Comb. By hand.
While the MMU holds the core (stall) and the walker is not using the lane, the core does not ask for the bus."""

SIG = (("addr", 32), ("store_data", 32), ("memtype", 3), ("memsrc", 2), ("valid", 1), ("xcpt", 1), ("memwrite", 1), ("kill", 1),
       ("dmem_we", 1), ("dmem_wdata", 32))


def golden_lane_mux(busy, ptw_req, ptw_addr, stall, core_req, addr, store_data, memtype, memsrc, valid, xcpt, memwrite, kill, dmem_we,
                    dmem_wdata):
    i = locals()
    if busy & 1:
        o = {"addr_o": ptw_addr & 0xFFFFFFFF, "store_data_o": 0, "memtype_o": 2, "memsrc_o": 1, "valid_o": 1, "xcpt_o": 0, "memwrite_o": 0,
             "kill_o": 0, "dmem_we_o": 0, "dmem_wdata_o": 0, "req": ptw_req & 1}
    else:
        o = {f"{n}_o": i[n] & ((1 << w) - 1) for n, w in SIG}
        o["req"] = int(bool(core_req & 1) and not stall & 1)
    return o


def vectors(rng):
    return [{"busy": rng.getrandbits(1), "ptw_req": rng.getrandbits(1), "ptw_addr": rng.getrandbits(32), "stall": rng.getrandbits(1),
             "core_req": rng.getrandbits(1), **{n: rng.getrandbits(w) for n, w in SIG}} for _ in range(3000)]
