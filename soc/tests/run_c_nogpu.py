# Build one C test (hart 0 only, the others park) and run it on a CPU-only netlist (isa_quad_tb: ends when 0x80FFF000 is written); prints the result line.
# usage: python3 demos/quad-soc/tests/run_c_nogpu.py <netlist dir> <c file> [-march=...]
import sys, struct, subprocess, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import vlsim
GCC = "/home/aura/tools/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc"
LINK = "ENTRY(_start)\nSECTIONS { . = 0x80000000; .text : { *(.text.init) *(.text*) *(.rodata*) } .data : { *(.data*) } .bss : { *(.bss*) } }\n"
CRT_PARK = ".section .text.init\n.globl _start\n_start:\n  li t0, -1\n  csrw pmpaddr0, t0\n  li t0, 0x1f\n  csrw pmpcfg0, t0\n  csrr t0, mhartid\n  bnez t0, 2f\n  li sp, 0x80F00000\n  call main\n1: j 1b\n2: j 2b\n"
net, src = Path(sys.argv[1]), sys.argv[2]
ALL = "--all-harts" in sys.argv       # every hart runs the test (the C file provides _start); default: hart 0 only
args = [a for a in sys.argv[3:] if not a.startswith("--")]
march = args[0] if args else "rv32imac_zicsr"
CRT = "" if ALL else CRT_PARK
with tempfile.TemporaryDirectory() as t:
    t = Path(t); (t / "crt.S").write_text(CRT); (t / "l.ld").write_text(LINK)
    r = subprocess.run([GCC, f"-march={march}", "-mabi=ilp32", "-O2", "-ffreestanding", "-nostdlib", "-nostartfiles", "-static", "-T", str(t / "l.ld"),
                        *([] if ALL else [str(t / "crt.S")]), src, "-o", str(t / "t.elf")], capture_output=True, text=True)
    if r.returncode: print(r.stderr[:2000]); sys.exit(1)
    subprocess.run([GCC[:-3] + "objcopy", "-O", "binary", str(t / "t.elf"), str(t / "t.bin")], check=True)
    b = (t / "t.bin").read_bytes(); b += b"\0" * (-len(b) % 4)
    (t / "t.hex").write_text("\n".join("%08x" % struct.unpack("<I", b[i:i + 4])[0] for i in range(0, len(b), 4)) + "\n")
    exe = vlsim.build(net, Path(__file__).parent / __import__("os").environ.get("TB", "isa_quad_tb.v"))
    out = vlsim.run(exe, [f"+HEX={t / 't.hex'}", "+TOHOST=80fff000", f"+LIMIT={__import__('os').environ.get('LIMIT', '2000000')}"])
print("\n".join(l for l in out.splitlines() if l.startswith(("PASS", "FAIL", "MON"))))
