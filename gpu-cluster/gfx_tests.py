"""Graphics on the GPU cluster, on the quad-core SoC's generated Verilog: every core draws its own scene.

    python3 demos/gpu-cluster/gfx_tests.py <assembled netlist dir> [--scenes flat,gouraud:3,...] [--limit CYCLES] [--out DIR]

Hart 0 (the others park) loads the triangle rasteriser (demos/simt-gpu/gfx/sw/tri_rast.c) into every core through the broadcast slot,
loads each core's scene (clear colour, triangles, texture, depth clear) into its own slot, starts all cores with one write and waits
for every STATUS to say done. The testbench then reads each core's video memory (work copy) directly, and this script compares every
pixel of every frame (320 x 240, RGB565) with the frame model (demos/simt-gpu/gfx/scenes.py), and writes each frame and a contact
sheet as PNG into --out. A scene is name or name:seed.
"""
import re, struct, subprocess, sys, tempfile, zlib
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "demos" / "gpu-soc"))
import gpu_tests as gt  # noqa: E402  (also puts demos/simt-gpu and its gfx folder on the path)
import run_kernel, scenes, run_g2a  # noqa: E402,E401
sys.path.insert(0, str(ROOT / "demos" / "quad-soc" / "tests"))
import vlsim  # noqa: E402

cp = gt.cp
argv = sys.argv[1:]
net = Path(argv[0])
opt = lambda k, d=None: next((argv[i + 1] for i, a in enumerate(argv) if a == f"--{k}"), d)  # noqa: E731
DEFAULT = "flat,gouraud,tex_small,blend_small,depth_small,cube_small,gouraud:3,flat:3,cube,depth_small:3"
SCENES = [(s.split(":")[0], int(s.split(":")[1]) if ":" in s else 7) for s in opt("scenes", DEFAULT).split(",")]
N = len(SCENES)
LIMIT = int(opt("limit", 40_000_000))
OUT = Path(opt("out", str(HERE / "out" / "frames")))
W, H, M = 320, 240, 0xFFFFFFFF
CRT = (".section .text.init\n.globl _start\n_start:\n  csrr t0, mhartid\n  bnez t0, 2f\n  li sp, 0x80F00000\n  call main\n"
       "1: j 1b\n2: j 2b\n")


def png(path, w, h, rgb):
    raw = b"".join(b"\0" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & M)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
                     chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def rgb_bytes(px):
    out = bytearray()
    for p in px:
        out += bytes(((p >> 11 & 31) * 255 // 31, (p >> 5 & 63) * 255 // 63, (p & 31) * 255 // 31))
    return bytes(out)


def build(tmp):
    elf = tmp / "tri_rast.elf"
    subprocess.run([run_kernel.GCC, *run_kernel.CFLAGS, "-T", str(gt.GPU / "sw" / "link.ld"), str(gt.GPU / "sw" / "crt0.S"),
                    str(gt.GPU / "gfx" / "sw" / "tri_rast.c"), "-o", str(elf)], check=True)
    import simt
    syms = run_kernel.load_elf(simt.Gpu(simt.Config()), elf)
    wr = []
    for a, seg in cp.elf_segments(elf):
        wr += [(15, gt.soc_addr(addr), v) for addr, v in gt.words(a, seg)]
    fills, wants = [], []
    for k, (name, seed) in enumerate(SCENES):
        clear, tris = scenes.scene(name, seed)
        tex, zclear = scenes.texture(name), scenes.depth_clear(name)
        wants.append(scenes.frame(clear, tris, tex, zclear))
        data = run_g2a.scene_bytes(syms, clear, tris, tex, None)
        wr += [(k, gt.soc_addr(a), v) for a, raw in data.items() for a, v in gt.words(a, raw)]
        if zclear is not None:
            fills.append((k, gt.soc_addr(0x4004_0000), W * H // 2, zclear << 16 | zclear))
    return wr, fills, syms["_start"][0], wants


def source(wr, fills, start):
    def arr(name, rows, cols):
        body = ",".join("{" + ",".join(f"0x{v & M:x}u" for v in r) + "}" for r in rows) or "{" + ",".join("0" for _ in range(cols)) + "}"
        return f"static const uint32_t {name}[][{cols}] = {{{body}}};\n#define N_{name} {len(rows)}\n"
    n_fills = len(fills)
    return f"""#include <stdint.h>
#define REG(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define TOHOST REG({gt.TOHOST:#x})
#define SLOT(k) ((uint32_t)(k) << 21)
{arr("WR", wr, 3)}{arr("FIL", fills, 4)}
static uint32_t rd(uint32_t a) {{ (void)REG(a); return REG(a); }}
static void fail(uint32_t code) {{ TOHOST = code * 2 + 1; for (;;) ; }}
int main(void) {{
    for (uint32_t i = 0; i < N_WR; i++) REG(WR[i][1] | SLOT(WR[i][0])) = WR[i][2];
    for (uint32_t f = 0; f < {n_fills}u; f++)
        for (uint32_t j = 0; j < FIL[f][2]; j++) REG((FIL[f][1] + 4 * j) | SLOT(FIL[f][0])) = FIL[f][3];
    REG(0x30000000u | SLOT(15) | 4) = {start:#x}u;
    REG(0x30000000u | SLOT(15) | 8) = 0;
    REG(0x30000000u | SLOT(15)) = 1;
    for (uint32_t k = 0; k < {N}; k++) {{
        uint32_t st;
        do st = rd(0x3000000Cu | SLOT(k)); while (!(st & 6));
        if (st & 4) fail(1 + k);
    }}
    TOHOST = 1;
    for (;;) ;
}}
"""


def image(src, tmp):
    (tmp / "t.c").write_text(src)
    (tmp / "crt.S").write_text(CRT)
    (tmp / "link.ld").write_text(gt.LINK)
    gcc = run_kernel.GCC
    r = subprocess.run([gcc, "-march=rv32imac_zicsr", "-mabi=ilp32", "-O2", "-ffreestanding", "-nostdlib", "-nostartfiles", "-static",
                        "-T", str(tmp / "link.ld"), str(tmp / "crt.S"), str(tmp / "t.c"), "-o", str(tmp / "t.elf")], capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr[:2000])
    subprocess.run([gcc[:-3] + "objcopy", "-O", "binary", str(tmp / "t.elf"), str(tmp / "t.bin")], check=True)
    b = (tmp / "t.bin").read_bytes()
    b += b"\0" * (-len(b) % 4)
    (tmp / "t.hex").write_text("\n".join("%08x" % struct.unpack("<I", b[i:i + 4])[0] for i in range(0, len(b), 4)) + "\n")
    return tmp / "t.hex"


OUT.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as t:
    tmp = Path(t)
    wr, fills, start, wants = build(tmp)
    print(f"{N} scenes: " + ", ".join(f"{n}:{s}" for n, s in SCENES) + f"; {len(wr)} words written, {len(fills)} depth clears", flush=True)
    hexf = image(source(wr, fills, start), tmp)
    (tmp / "dump_frames.vh").write_text("".join(
        f'      $sformat(fn, "%0s/f{k}_{b}.hex", outdir); $writememh(fn, dut.u_u_gpu{k}__vwbank{b}.mem);\n' for k in range(N) for b in range(4)))
    dumps = OUT / "dumps"  # kept, so that a later run with --reuse only redoes the comparison and the pictures
    dumps.mkdir(exist_ok=True)
    if "--reuse" in argv:
        val, cyc = 1, int((dumps / "cycles.txt").read_text())
    else:
        exe = vlsim.build(net, HERE / "tests" / "gpu_tb.v", includes=[tmp], defines=["DUMPFRAMES"])
        out = vlsim.run(exe, [f"+HEX={hexf}", f"+LIMIT={LIMIT}", f"+OUT={dumps}"])
        m = re.search(r"TOHOST (\d+) (\d+)", out)
        val, cyc = (int(m.group(1)), int(m.group(2))) if m else (None, None)
        if val == 1:
            (dumps / "cycles.txt").write_text(str(cyc))
    if val != 1:
        sys.exit("FAIL the program did not finish cleanly: " + (f"TOHOST {val}" + (f" (core {(val - 1) // 2 - 1} stopped with an error)" if val and 1 < val <= 2 * N + 1 else "")
                                                               if val else "no result within the cycle limit"))
    print(f"all {N} cores done after {cyc} cycles", flush=True)
    ok = True
    sheet_cols = 5
    rows = (N + sheet_cols - 1) // sheet_cols
    sheet = [bytearray(W * sheet_cols * 3) for _ in range(H * rows)]
    for k, (name, seed) in enumerate(SCENES):
        banks = [[int(x, 16) for line in (dumps / f"f{k}_{b}.hex").read_text().splitlines() if not line.startswith(("//", "@")) for x in line.split()]
                 for b in range(4)]
        got = [banks[p % 4][p // 4] for p in range(W * H)]
        bad = [p for p in range(W * H) if got[p] != wants[k][p]]
        ok &= not bad
        nonbg = sum(1 for p in range(W * H) if got[p] != got[0])
        print(("PASS " if not bad else "FAIL ") + f"core {k} {name}:{seed}: {W * H - len(bad)} of {W * H} pixels match the model, {nonbg} pixels differ from the corner colour"
              + ("" if not bad else f" (first mismatch at x={bad[0] % W}, y={bad[0] // W}: got {got[bad[0]]:04x} want {wants[k][bad[0]]:04x})"))
        png(OUT / f"core{k}_{name}_{seed}.png", W, H, rgb_bytes(got))
        rgb = rgb_bytes(got)
        r0, c0 = divmod(k, sheet_cols)
        for y in range(H):
            sheet[r0 * H + y][c0 * W * 3:(c0 + 1) * W * 3] = rgb[y * W * 3:(y + 1) * W * 3]
    png(OUT / "contact_sheet.png", W * sheet_cols, H * rows, b"".join(bytes(r) for r in sheet))
    print(f"images: {OUT}")
sys.exit(0 if ok else 1)
