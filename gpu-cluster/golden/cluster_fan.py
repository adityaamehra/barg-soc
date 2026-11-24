"""Golden model of the per-core enable of the GPU cluster (block `cluster_fan`). Combinational. Written by hand."""


def golden_cluster_fan(host_en, slot):
    slot &= 0xF
    return {f"en{i}": int(bool(host_en & 1) and slot in (i, 15)) for i in range(10)}


def vectors(rng):
    return [{"host_en": rng.getrandbits(1), "slot": s} for s in range(16) for _ in range(8)] + \
           [{"host_en": rng.getrandbits(1), "slot": rng.getrandbits(4)} for _ in range(500)]
