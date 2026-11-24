"""Golden model of the status aggregate of the GPU cluster (block `cluster_status`). Combinational. Written by hand."""

N = 10


def golden_cluster_status(running0, running1, running2, running3, running4, running5, running6, running7, running8, running9, done0, done1, done2, done3, done4, done5, done6, done7, done8, done9, error0, error1, error2, error3, error4, error5, error6, error7, error8, error9, diverged0, diverged1, diverged2, diverged3, diverged4, diverged5, diverged6, diverged7, diverged8, diverged9):
    i = locals()
    bits = lambda p: [i[f"{p}{k}"] & 1 for k in range(N)]  # noqa: E731
    return {"running": int(any(bits("running"))), "done": int(all(bits("done"))), "error": int(any(bits("error"))),
            "diverged": int(any(bits("diverged")))}


def vectors(rng):
    out = []
    for _ in range(2000):
        density = rng.choice([0.0, 0.1, 0.5, 0.9, 1.0])
        out.append({f"{p}{k}": int(rng.random() < density) for p in ("running", "done", "error", "diverged") for k in range(N)})
    return out
