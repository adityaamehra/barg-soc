"""Golden model of `hart_memif`: one hart's memory requests and run signal. Combinational. Written by hand."""


def golden_hart_memif(core_req, mmu_stall, imiss, ptw_req, ifq, grant):
    core_eff = core_req & 1 & (1 - (mmu_stall & 1)) & (1 - (imiss & 1))
    req = core_eff | (ptw_req & 1) | (ifq & 1)
    kind = 2 if ifq & 1 else 1 if ptw_req & 1 else 0
    return {"req": req, "kind": kind, "stall": (mmu_stall | imiss) & 1, "run": (1 - (core_req & 1)) | (grant & 1)}


def vectors(rng):
    return [{k: rng.getrandbits(1) for k in ("core_req", "mmu_stall", "imiss", "ptw_req", "ifq", "grant")} for _ in range(300)]
