"""Build and run the interrupt tests of the quad-core SoC and check their results.

    python3 demos/quad-soc/tests/run_irq4.py <assembled netlist dir> [--old] [--only=msipring,mtip]

<netlist dir> holds top.v and blocks.v (demos/linux-soc/assemble.py output of design-quad4.json). --old: the netlist without the PLIC.
"""
import os
import re, struct, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vlsim

HERE = Path(__file__).parent
GCC = Path("/home/aura/tools/xpack-riscv-none-elf-gcc-15.2.0-1/bin")
net = Path(sys.argv[1])
old = "--old" in sys.argv
only = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--only=")), None)


def build(src, tmp):
    elf, binf = tmp / f"{src.stem}.elf", tmp / f"{src.stem}.bin"
    subprocess.run([str(GCC / "riscv-none-elf-gcc"), "-march=rv32imac_zicsr_zifencei", "-mabi=ilp32", "-nostdlib", "-Wl,-Ttext=0x80000000",
                    "-o", str(elf), str(src)], check=True)
    subprocess.run([str(GCC / "riscv-none-elf-objcopy"), "-O", "binary", str(elf), str(binf)], check=True)
    b = binf.read_bytes() + b"\0" * ((-len(binf.read_bytes())) % 4)
    hexf = tmp / f"{src.stem}.hex"
    hexf.write_text("\n".join("%08x" % struct.unpack("<I", b[i:i + 4])[0] for i in range(0, len(b), 4)) + "\n")
    return hexf


def run(tmp, vvp, hexf, args):
    out = vlsim.run(vvp, [f"+HEX={hexf}"] + args + os.environ.get("IRQ_PLUSARGS", "").split())
    if os.environ.get("IRQ_PLUSARGS"):
        print(out[-3000:])
    words = {int(m.group(1), 16): int(m.group(2), 16) for m in re.finditer(r"^W (\w+) (\w+)$", out, re.M)}
    end = re.search(r"^END (\d+)", out, re.M)
    return words, int(end.group(1)) if end else None


def check_ring(w):
    errs = [f"count of hart {h} is {w.get(0x4C4 + h)} (want 5)" for h in range(4) if w.get(0x4C4 + h) != 5]
    errs += [] if w.get(0x4C8) == 0x600D else [f"flag {w.get(0x4C8)} (want 600d)"]
    errs += [] if 0x4CC not in w else ["stray trap recorded"]
    return errs


def check_mtip(w):
    errs = []
    for h in range(4):
        if w.get(0x500 + h) != 0x80000007:
            errs.append(f"hart {h} mcause record {w.get(0x500 + h)} (want 80000007)")
        seen, prog = w.get(0x504 + h), w.get(0x508 + h)
        if seen is None or prog is None or not (prog <= seen < prog + 2500):   # never early; late by at most the handler's first memory accesses (memory latency)
            errs.append(f"hart {h} saw mtime {seen} for mtimecmp {prog} (want prog <= seen < prog + 2500)")
    errs += [] if 0x50C not in w else ["stray trap recorded"]
    return errs


def check_plic(w):
    errs = []
    for h, want in ((0, None), (1, None), (2, 2), (3, 3)):
        if w.get(0x544 + h) != want:
            errs.append(f"hart {h} claimed {w.get(0x544 + h)} (want {want})")
    for h, want in ((0, None), (1, None), (2, 2), (3, 1)):
        if w.get(0x548 + h) != want:
            errs.append(f"hart {h} took {w.get(0x548 + h)} external interrupts (want {want})")
    errs += [] if w.get(0x558) == 3 else [f"{w.get(0x558)} completions (want 3)"]
    errs += [] if 0x554 not in w else ["stray trap recorded"]
    return errs


def check_ps2(w):
    errs = []
    want = {0x580: 0xFA, 0x581: 0xAA, 0x582: 0xFA, 0x58A: 24, 0x58B: 0x80000009, 0x58C: 4, 0x58E: 0x09, 0x58F: 0x05, 0x590: 0xFB, 0x591: 5, 0x592: 3, 0x596: 24, 0x59F: 0x600D}
    for k, v in want.items():
        if w.get(k) != v:
            errs.append(f"word {k:#x} is {w.get(k) if w.get(k) is None else hex(w.get(k))} (want {v:#x})")
    got = [w.get(0x5C0 + i) for i in range(24)]
    if got != [0x140 + i for i in range(24)]:
        errs.append("burst of 24 keyboard bytes arrived as " + " ".join('--' if g is None else f'{g & 255:02x}' for g in got))
    errs += [] if 0x59E not in w else [f"stray trap recorded ({w[0x59E]:#x})"]
    return errs


TESTS = {
    "msipring": ("msipring4.S", ["+DONE=4c8", "+DONEVAL=600d", "+LO=4c0", "+HI=4ff"], check_ring, "ring of msip interrupts through all four harts, 5 rounds"),
    "plicmeip": ("plicmeip4.S", [], check_plic, "external interrupts through the PLIC: priority, threshold, enable, claim, complete, per hart", "plicmeip4_tb.v"),
    "ps2irq": ("ps2irq4.S", [], check_ps2, "PS/2 keyboard and mouse: reset handshake, machine external interrupts (PLIC context 0), supervisor external interrupt (context 1)", "ps2irq4_tb.v"),
    "mtip": ("mtip4.S", ["+DONE=503", "+DONEVAL=80000007", "+EXTRA=800", "+LO=500", "+HI=50f"], check_mtip, "timer interrupt on each of the four harts, none early"),
}
ok = True
with tempfile.TemporaryDirectory() as t:
    tmp = Path(t)
    compiled = {}

    def vvp_for(tb):
        if tb not in compiled:
            compiled[tb] = vlsim.build(net, HERE / tb, defines=["OLDTOP"] if old else [])
        return compiled[tb]

    for name, (src, args, checker, what, *tbs) in TESTS.items():
        if only and name not in only:
            continue
        words, cyc = run(tmp, vvp_for(tbs[0] if tbs else "irq_dump_tb.v"), build(HERE / src, tmp), args)
        errs = checker(words)
        ok &= not errs
        print(("PASS " if not errs else "FAIL ") + f"{name}: {what}" + (f" ({cyc} cycles)" if not errs else ""))
        for e in errs:
            print("   ", e)
sys.exit(0 if ok else 1)
