"""Golden model of `dkind`: does the execute-stage instruction access data memory, and is it a store for permissions. Comb. By hand.
amo_op 1 is LR (a load); every other atomic is a store for permissions."""


def golden_dkind(valid, memsrc, memwrite, is_amo, amo_op):
    v = bool(valid & 1)
    amo = bool(is_amo & 1)
    return {"access": int(v and ((memsrc & 3) == 1 or bool(memwrite & 1) or amo)),
            "store": int(bool(memwrite & 1) or (amo and (amo_op & 15) != 1)),
            "kind": 2 if (bool(memwrite & 1) or (amo and (amo_op & 15) != 1)) else 1}


def vectors(rng):
    return [{"valid": rng.getrandbits(1), "memsrc": rng.getrandbits(2), "memwrite": rng.getrandbits(1), "is_amo": rng.getrandbits(1),
             "amo_op": rng.getrandbits(4)} for _ in range(2000)]
