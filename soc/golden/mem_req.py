"""Golden model of the memory-stage request detector (block `mem_req`). Combinational. Written by hand."""


def golden_mem_req(valid, xcpt, kill, memsrc, memwrite, is_amo):
    return {"req": int(bool(valid & 1) and not xcpt & 1 and not kill & 1 and (memsrc & 3 == 1 or bool(memwrite & 1) or bool(is_amo & 1)))}


def vectors(rng):
    return [{"valid": rng.getrandbits(1), "xcpt": rng.getrandbits(1), "kill": rng.getrandbits(1), "memsrc": rng.getrandbits(2),
             "memwrite": rng.getrandbits(1), "is_amo": rng.getrandbits(1)} for _ in range(1000)]
