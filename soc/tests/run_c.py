# Build one C test (hart 0 only, the others park) and run it on a netlist; prints TOHOST and the nonzero RAM words in a range. Verilator.
# usage: python3 demos/quad-soc/tests/run_c.py <netlist dir> <c file> [lo hi]   (lo hi: hex word indices, default 3fc100 3fc13f)
import sys, re, struct, subprocess, tempfile
from pathlib import Path
sys.path.insert(0,'demos/quad-soc/tests')
import vlsim
GCC="/home/aura/tools/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc"
LINK="ENTRY(_start)\nSECTIONS { . = 0x80000000; .text : { *(.text.init) *(.text*) *(.rodata*) } .data : { *(.data*) } .bss : { *(.bss*) } }\n"
CRT=".section .text.init\n.globl _start\n_start:\n  li t0, -1\n  csrw pmpaddr0, t0\n  li t0, 0x1f\n  csrw pmpcfg0, t0\n  csrr t0, mhartid\n  bnez t0, 2f\n  li sp, 0x80F00000\n  call main\n1: j 1b\n2: j 2b\n"
ALL="--all-harts" in sys.argv; sys.argv=[a for a in sys.argv if a!="--all-harts"]
net=Path(sys.argv[1]); src=sys.argv[2]; lo=sys.argv[3] if len(sys.argv)>3 else "3fc100"; hi=sys.argv[4] if len(sys.argv)>4 else "3fc13f"
with tempfile.TemporaryDirectory() as t:
    t=Path(t); (t/'crt.S').write_text('' if ALL else CRT); (t/'l.ld').write_text(LINK)
    r=subprocess.run([GCC,"-march=rv32imac_zicsr","-mabi=ilp32","-O2","-ffreestanding","-nostdlib","-nostartfiles","-static","-T",str(t/'l.ld'),*([] if ALL else [str(t/'crt.S')]),src,"-o",str(t/'t.elf')],capture_output=True,text=True)
    if r.returncode: print(r.stderr[:2000]); sys.exit(1)
    subprocess.run([GCC[:-3]+"objcopy","-O","binary",str(t/'t.elf'),str(t/'t.bin')],check=True)
    b=(t/'t.bin').read_bytes(); b+=b"\0"*(-len(b)%4)
    (t/'t.hex').write_text("\n".join("%08x"%struct.unpack("<I",b[i:i+4])[0] for i in range(0,len(b),4))+"\n")
    exe=vlsim.build(net,Path('demos/gpu-cluster/tests/gpu_tb.v'))
    out=vlsim.run(exe,[f"+HEX={t/'t.hex'}",f"+LIMIT={__import__('os').environ.get('LIMIT', '600000')}",f"+LO={lo}",f"+HI={hi}"])
print("\n".join(l for l in out.splitlines() if l.startswith(("TOHOST","W ","P ","T ","F "))))
