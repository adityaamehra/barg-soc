#!/usr/bin/env python3
"""Write the Verilog of the quad-core Linux SoC for the ZCU104 into build/src (everything the Vivado flow reads).

    python3 demos/fpga/zcu104/export.py [out-dir]

Runs demos/quad-soc/tests/mk.sh --ext-mem (the final SoC with every feature on; the memory model is left out and the AXI4 master is a port), renames the design's top to
soc_core, and copies the board wrapper and the curated UART (barg_uart, barg_fifo). Then lints the whole set with Verilator.
"""
import re, shutil, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
args = [a for a in sys.argv[1:] if not a.startswith("--")]
GPUN = int(sys.argv[sys.argv.index("--gpu-cores") + 1]) if "--gpu-cores" in sys.argv else 10   # GPU cores kept; the others become empty stubs (outputs 0, 'done' outputs 1) that synthesis removes
if "--gpu-cores" in sys.argv: args = [a for a in args if a != str(GPUN)]
out = Path(args[0] if args else HERE / "build" / "src").resolve()
tmp = HERE / "build" / "net"
subprocess.run(["bash", str(ROOT / "demos/quad-soc/tests/mk.sh"), str(tmp), "--ext-mem", "--fpga-caches"], check=True)
out.mkdir(parents=True, exist_ok=True)
for f in out.glob("*.v"): f.unlink()
top = (tmp / "out" / "top.v").read_text()
top = re.sub(r"\bmodule top \(", "module soc_core (", top, count=1)
top = re.sub(r"(?m)^(\s*)wire(\s+)(net_n_q\d+_gclk;)", r'\1(* gated_clock = "true" *) wire\2\3', top)   # lets Vivado turn the cores' clock gates into clock enables (-gated_clock_conversion on)
top = top.replace("module soc_core (\n", "module soc_core (\n  input  wire        clk_pre,   // the clock before the SoC's own buffer: the cores' clock gates (BUFGCE) take it, like the ungated clock's BUFGCE\n", 1)
top = re.sub(r"(?m)^(\s*\w*_core_gate\s+u_c\d_core_gate\s*\(\.clk\()\w+(\))", r"\1clk_pre\2", top)
(out / "soc_core.v").write_text(top)
blocks = (tmp / "out" / "blocks.v").read_text()
def gate_bufgce(m):   # FPGA: the latch + AND clock gate becomes a BUFGCE (glitch-free clock gating cell); Verilator keeps the original
    return m.group(1) + "`ifdef VERILATOR\n" + m.group(2) + "`else\n  BUFGCE u_gate (.I(clk), .CE(en | rst), .O(gclk));\n`endif\nendmodule\n"
blocks = re.sub(r"(?s)(module c\d_core_gate \(.*?\);\n)(.*?)endmodule\n", gate_bufgce, blocks)
def stub(m):   # an empty module with the same ports
    text, k = m.group(0), int(m.group(1))
    if k < GPUN: return text
    hdr = text[:text.index(");") + 2]
    if re.search(r"\b(input|output|inout)\b", hdr):   # ANSI header
        decl = ""
    else:                                              # non-ANSI: the port declarations are statements in the body
        decl = "".join("  " + d.strip() + "\n" for d in re.findall(r"(?m)^\s*(?:input|output|inout)\b[^;]*;", text[len(hdr):]))
    outs = re.findall(r"output\s+(?:wire\s+|reg\s+)?(?:signed\s+)?(?:\[[^\]]*\]\s*)?(\w+)", hdr + decl)
    hdr, decl = (re.sub(r"output\s+reg\b", "output", x) for x in (hdr, decl))
    return hdr + "\n" + decl + "".join(f"  assign {o} = {1 if 'done' in o else 0};\n" for o in outs) + "endmodule\n"
if GPUN < 10: blocks = re.sub(r"(?ms)^module simt_gpu_core(\d+)__\w+.*?^endmodule\n", stub, blocks)
(out / "blocks.v").write_text(blocks)
for n in ("barg_uart.v", "barg_fifo.v"): shutil.copy(ROOT / "packages/ip/rtl" / n, out / n)
shutil.copy(HERE / "rtl" / "soc_zcu104.v", out / "soc_zcu104.v")
r = subprocess.run(["verilator", "--lint-only", "-Wno-fatal", "-Wno-lint", "-Wno-style", "--top-module", "soc_zcu104"] + [str(p) for p in sorted(out.glob("*.v"))], capture_output=True, text=True)
errs = [l for l in r.stderr.splitlines() if l.startswith("%Error")]
print("lint:", "clean" if not errs else "\n".join(errs[:10]))
sys.exit(1 if errs else 0)
