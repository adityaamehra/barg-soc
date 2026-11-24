"""Boot OpenSBI + Linux on the quad-core SoC's generated Verilog (Verilator), streaming the console.

    python3 demos/linux-soc/tests/boot_quad.py <assembled netlist dir> <image.bin> [--limit CYCLES] [--until "text"] [--beat N] [--log FILE]
                                               [--type "line1;line2" --type-start CYCLE]

Converts the flat image to words for 0x8000_0000, builds the netlist with linux_quad_tb.v (cached), runs it and prints the console as it
comes, stopping when --until text appears (for example the shell prompt) or at the cycle limit. --type feeds lines to the UART receiver
(each byte 2000 cycles apart) starting at --type-start.
"""
import subprocess, struct, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / "quad-soc" / "tests"))
import vlsim  # noqa: E402

argv = sys.argv[1:]
net, image = Path(argv[0]), Path(argv[1])
opt = lambda k, d=None: next((argv[i + 1] for i, a in enumerate(argv) if a == f"--{k}"), d)  # noqa: E731
limit, until, beat = opt("limit", "200000000"), opt("until"), opt("beat", "5000000")
logf = Path(opt("log", "/tmp/boot_quad.log"))
with tempfile.TemporaryDirectory() as t:
    tmp = Path(t)
    data = image.read_bytes()
    data += b"\0" * (-len(data) % 4)
    (tmp / "img.hex").write_text("".join(f"{w:08x}\n" for (w,) in struct.iter_unpack("<I", data)))
    args = [f"+HEX={tmp / 'img.hex'}", f"+LIMIT={limit}", f"+BEAT={beat}"]
    if opt("trap-trace"):
        args += ["+TRAPTRACE=1"]
    if opt("trace-at"):
        args += [f"+TRACEAT={opt('trace-at')}", f"+TRACELEN={opt('trace-len', '400')}"]
    if opt("type"):
        (tmp / "rx.hex").write_text("".join(f"{b:02x}\n" for line in opt("type").split(";") for b in (line + "\r").encode()))
        nbytes = sum(len(line + "\r") for line in opt("type").split(";"))
        args += [f"+RXFILE={tmp / 'rx.hex'}", f"+RXN={nbytes}", f"+RXSTART={opt('type-start', '0')}", f"+RXGAP={opt('type-gap', '20000')}"]
    exe = vlsim.build(net, HERE / "linux_quad_tb.v")
    t0 = time.time()
    p = subprocess.Popen([str(exe), *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    seen, hit = "", False
    with logf.open("w") as lf:
        while True:
            ch = p.stdout.read(1)
            if not ch:
                break
            sys.stdout.write(ch); sys.stdout.flush(); lf.write(ch); lf.flush()
            seen = (seen + ch)[-4000:]
            if until and until in seen:
                hit = True
                p.terminate()
                break
    p.wait()
    print(f"\n[{'stopped at the expected text' if hit else 'run ended'} after {time.time() - t0:.0f} s of real time]")
sys.exit(0 if hit or not until else 1)
