"""Four harts thrash their TLBs at the same time on the quad-core SoC (paging4.c). Verilator.

    python3 demos/quad-soc/tests/run_paging4.py <assembled netlist dir> [--limit CYCLES]
"""
import re, struct, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import vlsim  # noqa: E402

GCC = "/home/aura/tools/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc"
LINK = "ENTRY(_start)\nSECTIONS { . = 0x80000000; .text : { *(.text.init) *(.text*) *(.rodata*) } .data : { *(.data*) } .bss : { *(.bss*) } }\n"
CRT = ".section .text.init\n.globl _start\n_start:\n  li t0, -1\n  csrw pmpaddr0, t0\n  li t0, 0x1f\n  csrw pmpcfg0, t0\n  csrr t0, mhartid\n" + ("  bnez t0, 2f\n" if "--solo" in sys.argv else "") + "  li sp, 0x80F00000\n  slli t1, t0, 16\n  sub sp, sp, t1\n  call main\n1: j 1b\n2: j 2b\n"
net = Path(sys.argv[1])
limit = sys.argv[sys.argv.index("--limit") + 1] if "--limit" in sys.argv else "3000000"
with tempfile.TemporaryDirectory() as t:
    tmp = Path(t)
    (tmp / "crt.S").write_text(CRT)
    (tmp / "link.ld").write_text(LINK)
    r = subprocess.run([GCC, "-march=rv32imac_zicsr", "-mabi=ilp32", "-O2", "-ffreestanding", "-nostdlib", "-nostartfiles", "-static",
                        *(["-DNH=1"] if "--solo" in sys.argv else []), *(["-DBARE"] if "--bare" in sys.argv else []), "-T", str(tmp / "link.ld"), str(tmp / "crt.S"), str(HERE / (sys.argv[sys.argv.index("--src") + 1] if "--src" in sys.argv else "paging4.c")), "-o", str(tmp / "t.elf")], capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr[:2000])
    subprocess.run([GCC[:-3] + "objcopy", "-O", "binary", str(tmp / "t.elf"), str(tmp / "t.bin")], check=True)
    b = (tmp / "t.bin").read_bytes()
    b += b"\0" * (-len(b) % 4)
    (tmp / "t.hex").write_text("\n".join("%08x" % struct.unpack("<I", b[i:i + 4])[0] for i in range(0, len(b), 4)) + "\n")
    exe = vlsim.build(net, HERE.parents[1] / "gpu-cluster" / "tests" / "gpu_tb.v")
    out = vlsim.run(exe, [f"+HEX={tmp / 't.hex'}", f"+LIMIT={limit}", "+LO=3fc040", "+HI=3fc08f"])
m = re.search(r"TOHOST (\d+) (\d+)", out)
diag = re.findall(r"^W (\w+) (\w+)$", out, re.M)
val, cyc = (int(m.group(1)), int(m.group(2))) if m else (None, None)
if val == 1:
    nh = 1 if "--solo" in sys.argv else 4
    print(f"PASS {nh} hart(s), own page table each, 32 pages through 8-entry TLBs, walks concurrent; virtual and physical views agree ({cyc} cycles)")
elif not val:
    print("FAIL no result within the cycle limit")
    print("   trap record words:", diag)
else:
    code = (val - 1) // 2
    if code >> 24 == 7:
        print(f"FAIL hart {code & 255} took an unexpected trap: " + ", ".join(f"word {i}={v}" for i, v in diag))
        sys.exit(1)
    h, w = divmod(code, 100000)
    w -= 1
    print(f"FAIL hart {h}: round {w >> 12}, page {w >> 4 & 255}, " + ("virtual read wrong" if w & 15 == 0 else "physical frame wrong"))
sys.exit(0 if val == 1 else 1)
