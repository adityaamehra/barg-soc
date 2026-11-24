"""Verilator build-and-run helper for the quad-core SoC's tests (about 50x faster than Icarus on this design).

    import vlsim
    exe = vlsim.build(netlist_dir, testbench_file, includes=[dir, ...], defines=["NAME"])   # cached by the content of its inputs
    out = vlsim.run(exe, ["+HEX=image.hex", "+LIMIT=1000"])                                 # the simulation's output text

The netlist is <netlist_dir>/top.v and blocks.v (demos/linux-soc/assemble.py). The testbench's first module is the top. Verilator is
2-state: every register starts at 0 (the designs reset what they need). Warnings are not fatal (the generated netlist has width and
loop warnings that Icarus also accepts); the build log is kept next to the binary.
"""
import hashlib, os, re, subprocess
from pathlib import Path

OSS = Path("/home/aura/tools/oss-cad-suite/bin")
CACHE = Path(os.environ.get("VLSIM_CACHE", "/tmp/vlsim-cache"))
ENV = {**os.environ, "PATH": f"{OSS}:{os.environ['PATH']}"}


def build(net, tb, includes=(), defines=(), jobs=24, extra=()):
    net, tb = Path(net), Path(tb)
    defines = list(defines)
    if "u_l3_array" in (net / "top.v").read_text() and "HIER" not in defines:     # the cache hierarchy: the testbenches read the memory through its last-level cache
        defines.append("HIER")
    if "u_c0_dcache_ctl" in (net / "top.v").read_text() and "MEMSYS" not in defines:         # the memory-system build (data caches): its testbench probes the caches
        defines.append("MEMSYS")
    if "gpio_oe" in (net / "top.v").read_text() and "PERIPH" not in defines:      # the peripheral window (build_quad5 --periph): the testbenches tie its pins off
        defines.append("PERIPH")
    if "ps2k_clk_i" in (net / "top.v").read_text() and "PS2" not in defines:      # the PS/2 keyboard and mouse ports: the testbenches tie their lines idle
        defines.append("PS2")
    includes = [*includes, Path(__file__).parent]
    h = hashlib.sha1()
    for f in (net / "top.v", net / "blocks.v", tb, *[p for d in includes for p in sorted(Path(d).glob("*.vh"))]):
        h.update(f.read_bytes())
    for f in extra:
        h.update(Path(f).read_bytes())          # extra sources (C++ for DPI-C, more Verilog)
    threads = int(os.environ.get("VL_THREADS", "0"))      # multithreaded model: the simulator then uses this many cores (busy-waiting)
    h.update(repr((sorted(defines), [str(i) for i in includes], threads)).encode())
    d = CACHE / h.hexdigest()[:16]
    exe = d / "obj" / "Vtb"
    if exe.exists():
        return exe
    d.mkdir(parents=True, exist_ok=True)
    top = re.search(r"^\s*module\s+(\w+)", tb.read_text(), re.M).group(1)
    cmd = [str(OSS / "verilator"), "--binary", "--timing", "-Wno-fatal", "-Wno-lint", "-Wno-style", "-Wno-WIDTH", "-Wno-UNOPTFLAT",
           "-Wno-MULTIDRIVEN", "-Wno-fatal", "-O3", "-j", str(jobs), *(["--threads", str(threads)] if threads else []), "--top-module", top, "--Mdir", str(d / "obj"), "-o", "Vtb",
           *[f"-I{i}" for i in includes], *[f"-D{x}" for x in defines], str(net / "top.v"), str(net / "blocks.v"), str(tb), *[str(f) for f in extra]]
    r = subprocess.run(cmd, capture_output=True, text=True, env=ENV)
    (d / "build.log").write_text(r.stdout + r.stderr)
    if r.returncode or not exe.exists():
        raise SystemExit("verilator failed (log: %s):\n%s" % (d / "build.log", (r.stdout + r.stderr)[-1500:]))
    return exe


def run(exe, args=(), timeout=36000):
    r = subprocess.run([str(exe), *args], capture_output=True, text=True, timeout=timeout)
    return r.stdout + r.stderr
