"""Golden model of `mem_arb`: arbiter and sequencer of the memory transactions of four harts. Clocked. Written by hand.
Outputs before the edge (combinational from the state and the inputs); None before the first reset."""

NAMES = ([f"sel{k}" for k in range(4)] + [f"bsel{k}" for k in range(4)] + [f"grant{k}" for k in range(4)] +
         ["eng_start", "eng_we", "eng_line", "eng_src", "rdone", "wdone"])


def golden_mem_arb(trace):
    st = None
    out = []
    for i in trace:
        if st is None:
            out.append({n: None for n in NAMES})
        else:
            s, cur, core, last = st
            o = {n: 0 for n in NAMES}
            elig = [(i[f"req{k}"] & 1) and i[f"kind{k}"] != 3 for k in range(4)]
            nxt = st
            if s == 0:
                w = next(((last + d) % 4 for d in (1, 2, 3, 4) if elig[(last + d) % 4]), None)
                if w is not None:
                    o[f"sel{w}"] = 1
                    kw = i[f"kind{w}"]
                    o[f"bsel{w}"] = int(kw == 0)
                    ram, store, amo = i["is_ram"] & 1, i["c_store"] & 1, i["c_amo"] & 1
                    cstore = kw == 0 and ram and store and not amo
                    camo = kw == 0 and ram and amo
                    cload = kw == 0 and ram and not store and not amo
                    dev = kw == 0 and not ram
                    start = (cstore or camo or cload or kw == 1 or kw == 2) and (i["eng_ready"] & 1)
                    o["eng_start"] = int(bool(start))
                    o["eng_we"] = int(bool(start and cstore))
                    o["eng_line"] = int(bool(start and kw == 2))
                    o["eng_src"] = kw
                    if dev:
                        o[f"grant{w}"] = 1
                    if start:
                        nxt = (2 if cstore else 3 if camo else 1, w, int(kw == 0), w)
                    elif dev:
                        nxt = (0, cur, core, w)
            elif s in (1, 2, 3, 4, 5):
                o[f"sel{cur}"] = 1
                o[f"bsel{cur}"] = core
                done = i["eng_done"] & 1
                if s in (1, 2, 5):
                    o[f"grant{cur}"] = done
                    o["rdone"] = done if s == 1 else 0
                    o["wdone"] = done if s in (2, 5) else 0
                    if done:
                        nxt = (0, cur, core, last)
                elif s == 3:
                    o["rdone"] = done
                    if done:
                        nxt = (4, cur, core, last)
                else:   # 4: the atomic decision
                    we = i["c_dmem_we"] & 1
                    rdy = i["eng_ready"] & 1
                    o["eng_start"] = we & rdy
                    o["eng_we"] = we & rdy
                    o[f"grant{cur}"] = 1 - we
                    if we and rdy:
                        nxt = (5, cur, core, last)
                    elif not we:
                        nxt = (0, cur, core, last)
            else:       # 6, 7
                nxt = (0, cur, core, last)
            out.append(o)
            st = nxt
        if i["rst"] & 1:
            st = (0, 0, 0, 3)
    return out


def traces(rng):
    out = []
    for _ in range(80):
        t = [{"rst": 1, **{f"req{k}": 0 for k in range(4)}, **{f"kind{k}": 0 for k in range(4)}, "is_ram": 0, "c_store": 0, "c_amo": 0,
              "c_dmem_we": 0, "eng_ready": 1, "eng_done": 0}]
        for _ in range(220):
            t.append({"rst": int(rng.random() < 0.005), **{f"req{k}": int(rng.random() < 0.5) for k in range(4)},
                      **{f"kind{k}": rng.choice([0, 0, 0, 1, 2, 3]) for k in range(4)}, "is_ram": int(rng.random() < 0.75),
                      "c_store": int(rng.random() < 0.35), "c_amo": int(rng.random() < 0.25), "c_dmem_we": int(rng.random() < 0.6),
                      "eng_ready": int(rng.random() < 0.85), "eng_done": int(rng.random() < 0.3)})
        out.append(t)
    return out
