"""Find where the generated RTL stops behaving like the design's netlist of golden models, for one kernel.

    python3 demos/simt-gpu/compare_commits.py gemm_shared

Both are run on the same kernel; each records every committed instruction (warp, pc) in order. Per warp, the two sequences
must be equal; the first difference, with its neighbours, says where to look.
"""

import json
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "model"))
import check_pipeline as cp  # noqa: E402
import run_kernel  # noqa: E402
import run_rtl  # noqa: E402


def golden_commits(name: str, seed: int = 1) -> list[tuple[int, int]]:
    design = json.loads((HERE / "design.json").read_text())
    with tempfile.TemporaryDirectory() as tmp:
        from simt import Gpu, Config
        elf = run_kernel.compile_kernel(name, Path(tmp))
        ref = Gpu(Config())
        syms = run_kernel.load_elf(ref, elf)
        segments = cp.elf_segments(elf)
    inputs, _ = run_kernel.CASES[name](random.Random(seed))
    net = cp.Netlist(design)
    ids = {n["name"]: n["id"] for n in design["nets"]}
    host = cp.Host(net)
    net.top["rst"] = 1
    host.idle(2)
    net.top["rst"] = 0
    for addr, data in segments:
        host.write_bytes(addr, data)
    for sym, raw in inputs.items():
        host.write_bytes(syms[sym][0], raw)
    host.write(0x3000_0004, syms["_start"][0])
    host.write(0x3000_0000, 1)
    out = []
    while True:
        net.settle()
        if net.out("done") or net.out("error"):
            break
        if net.value[ids["advance"]] and net.value[ids["x_valid"]]:
            out.append((net.value[ids["x_wid"]], net.value[ids["x_pc"]], net.value[ids["rf0_we"]],
                        net.value[ids["rf0_wdata"]] if net.value[ids["rf0_we"]] else 0))
        host.idle()
    return out


def main() -> int:
    name = sys.argv[1]
    rtl = run_rtl.run_on_rtl(name, trace="commits")["commits"]
    gold = golden_commits(name)
    for w in range(4):
        a = [(pc, we, d if we else 0) for wid, pc, we, d in rtl if wid == w]
        b = [(pc, we, d if we else 0) for wid, pc, we, d in gold if wid == w]
        n = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), None)
        if n is None and len(a) == len(b):
            print(f"warp {w}: {len(a)} commits, identical")
            continue
        n = min(len(a), len(b)) if n is None else n
        print(f"warp {w}: RTL {len(a)} commits, golden {len(b)}; first difference at commit {n}  (pc, lane-0 write enable, data)")
        print("   RTL    :", [(hex(p), w_, hex(d)) for p, w_, d in a[max(0, n - 2):n + 3]])
        print("   golden :", [(hex(p), w_, hex(d)) for p, w_, d in b[max(0, n - 2):n + 3]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
