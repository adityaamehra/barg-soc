"""Stage G1b check on the design itself: the graphics kernel on the netlist of golden models of `simt-gpu-gfx`.

    python3 demos/simt-gpu/gfx/check_netlist.py [--rows=24]
    python3 demos/simt-gpu/gfx/check_netlist.py --kernel=tri_rast [--scene=small]    (G2b: the raster unit, rows 0..39 compared)

The netlist is gfx/design.json wired block by block, every block a hand-written golden model (gfx/golden/ first, then the core's
golden/). The host loads the kernel (kernels.kernel_g1b), starts it, waits for done, and reads the rows the kernel drew back through the
video-memory window. They must equal the independent frame model (kernels.frame_g1b) and the instruction-level model's frame.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "model"))
import check_pipeline as cp  # noqa: E402
import kernels  # noqa: E402
import simt  # noqa: E402

VRAM = 0x4000_0000


def run(rows: int) -> int:
    cp.GOLDEN_DIRS[:] = [HERE / "golden", HERE.parent / "golden"]
    design = json.loads((HERE / "design.json").read_text())
    code = kernels.kernel_g1b(rows)
    want = kernels.frame_g1b(rows)
    ref = simt.Gpu(simt.Config())
    ref.write(0, code)
    ref.launch(0)
    ref.run(5_000_000)
    assert ref.frame[: rows * 320] == want[: rows * 320], "the instruction-level model and the frame model disagree"

    net = cp.Netlist(design)
    host = cp.Host(net)
    net.top["rst"] = 1
    host.idle(2)
    net.top["rst"] = 0
    host.write_bytes(0, code)
    host.write(0x3000_0004, 0)
    host.write(0x3000_0008, 0)
    start = net.cycle
    host.write(0x3000_0000, 1)
    while True:
        net.settle()
        if net.out("done") or net.out("error"):
            break
        if net.cycle - start > 3_000_000:
            raise AssertionError("no done")
        host.idle()
    cycles = net.cycle - start
    if net.out("error"):
        info = host.read(0x3000_0014)
        raise AssertionError(f"the core stopped: cause {info & 15}, warp {info >> 8 & 3}, pc 0x{host.read(0x3000_0010):08x}")
    bad = 0
    for p in range(0, rows * 320, 2):
        w = host.read(VRAM + 2 * p)
        for half, pix in ((0, p), (1, p + 1)):
            if (w >> 16 * half & 0xFFFF) != want[pix]:
                bad += 1
                if bad <= 5:
                    print(f"  pixel (x {pix % 320}, y {pix // 320}): netlist 0x{w >> 16 * half & 0xFFFF:04x}, model 0x{want[pix]:04x}")
    print(f"G1b on the netlist: {cycles} cycles, {rows * 320} pixels read back, {'PASS' if not bad else f'FAIL, {bad} differ'}")
    return 0 if not bad else 1


def run_c(kernel: str, scene: str, rows: int = 40) -> int:
    """A C kernel of gfx/sw/ (tri, tri_rast) on a scene of gfx/scenes.py, on the netlist; the first `rows` rows are compared."""
    import subprocess
    import tempfile
    import run_kernel
    import run_g2a
    import scenes
    cp.GOLDEN_DIRS[:] = [HERE / "golden", HERE.parent / "golden"]
    design = json.loads((HERE / "design.json").read_text())
    clear, tris = scenes.scene(scene)
    tex = scenes.texture(scene)
    zclear = scenes.depth_clear(scene)
    want = scenes.frame(clear, tris, tex, zclear)
    with tempfile.TemporaryDirectory() as tmp:
        elf = Path(tmp) / "k.elf"
        subprocess.run([run_kernel.GCC, *run_kernel.CFLAGS, "-Werror=frame-larger-than=112", "-T", str(HERE.parent / "sw" / "link.ld"),
                        str(HERE.parent / "sw" / "crt0.S"), str(HERE / "sw" / f"{kernel}.c"), "-o", str(elf)], check=True)
        ref = simt.Gpu(simt.Config())
        syms = run_kernel.load_elf(ref, elf)
        segments = cp.elf_segments(elf)
    data = run_g2a.scene_bytes(syms, clear, tris, tex, zclear)
    for a, raw in data.items():
        ref.write(a, raw)
    ref.launch(syms["_start"][0])
    ref.run(50_000_000)
    assert ref.frame == want, "the instruction-level model and the frame model disagree"
    net = cp.Netlist(design)
    host = cp.Host(net)
    net.top["rst"] = 1
    host.idle(2)
    net.top["rst"] = 0
    for addr, seg in segments:
        host.write_bytes(addr, seg + bytes(-len(seg) % 4))
    for a, raw in data.items():
        host.write_bytes(a, raw + bytes(-len(raw) % 4))
    host.write(0x3000_0004, syms["_start"][0])
    host.write(0x3000_0008, 0)
    start = net.cycle
    host.write(0x3000_0000, 1)
    while True:
        net.settle()
        if net.out("done") or net.out("error"):
            break
        if net.cycle - start > 3_000_000:
            raise AssertionError("no done")
        host.idle()
    cycles = net.cycle - start
    if net.out("error"):
        info = host.read(0x3000_0014)
        raise AssertionError(f"the core stopped: cause {info & 15}, warp {info >> 8 & 3}, pc 0x{host.read(0x3000_0010):08x}")
    bad = 0
    for p in range(0, rows * 320, 2):
        w = host.read(VRAM + 2 * p)
        for half, pix in ((0, p), (1, p + 1)):
            if (w >> 16 * half & 0xFFFF) != want[pix]:
                bad += 1
                if bad <= 5:
                    print(f"  pixel (x {pix % 320}, y {pix // 320}): netlist 0x{w >> 16 * half & 0xFFFF:04x}, model 0x{want[pix]:04x}")
    print(f"{kernel} / {scene} on the netlist: {cycles} cycles, {rows * 320} pixels read back, {'PASS' if not bad else f'FAIL, {bad} differ'}")
    return 0 if not bad else 1


if __name__ == "__main__":
    kernel = next((a.split("=")[1] for a in sys.argv[1:] if a.startswith("--kernel=")), None)
    if kernel:
        sys.exit(run_c(kernel, next((a.split("=")[1] for a in sys.argv[1:] if a.startswith("--scene=")), "small")))
    sys.exit(run(int(next((a.split("=")[1] for a in sys.argv[1:] if a.startswith("--rows=")), 24))))
