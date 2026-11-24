#!/usr/bin/env python3
"""Boot Linux on the SoC's generated Verilog and use it from your terminal.

    python3 demos/linux-soc/run_linux.py                      # boot to the shell and type into it
    python3 demos/linux-soc/run_linux.py --keys "uname;ls /;free;fork"   # type these commands for you, each after the prompt, then leave
    python3 demos/linux-soc/run_linux.py --image other.bin    # another firmware image (a flat image for 0x8000_0000)
    python3 demos/linux-soc/run_linux.py --gpu --image ~/linux-work/pico-gpu/sbi/platform/generic/firmware/fw_payload.bin --frames /tmp/gpu   # with the GPU; `gpu` draws a scene

What runs: the quad-core SoC (four RV32IMAFDC harts, one FPU each, with Sv32 MMUs, CLINT, PLIC, UART, 64 MB RAM; the CPU-only build) as Verilog that
BARG generated, simulated with Verilator. OpenSBI starts, Linux 6.6 brings up the CPUs and runs BusyBox (a real shell with ash, ls, cat, ps, awk, ...;
its userland is hard-float, which is why the SoC has the F and D extensions). --image ~/linux-work/pico-fp/... gives the small init of sw/init.c instead. The first run builds the netlist and the simulator (about a minute); later runs start at once. The boot to the
prompt takes about two minutes of real time (about 110 million simulated clock cycles).

In the console: Ctrl-A x leaves, Ctrl-A a sends a Ctrl-A. Typing is slow on purpose: the SoC's UART has a one-byte receive register and Linux polls
it every 20 ms of simulated time, so a character is accepted about every 200,000 cycles (a few per real second). Type a command and wait.

Options: --image FILE, --keys "a;b", --until TEXT (leave when the console prints TEXT), --max-cycles N, --rebuild (rebuild the netlist and simulator).
"""
import argparse, hashlib, os, shutil, signal, struct, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "demos" / "quad-soc" / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
CACHE = Path(os.environ.get("BARG_SOC_CACHE", Path.home() / ".cache" / "barg-soc"))
os.environ.setdefault("VLSIM_CACHE", str(CACHE / "verilator"))
import vlsim  # noqa: E402

FW = Path("sbi") / "platform" / "generic" / "firmware" / "fw_payload.bin"
DEFAULT_IMAGE = Path.home() / "linux-work" / "pico-bb" / FW       # BusyBox (hard float, needs the FP SoC); pico-fp is the small init of sw/init.c with FP, pico the integer-only one


def netlist(rebuild: bool, gpu: bool = False, fp: bool = False, mem: bool = False, bp: bool = False, hier: bool = False, periph: bool = False, post: bool = False, tlb32: bool = False, wfi: bool = False, wa: bool = False, pmp: bool = False, ps2: bool = False) -> Path:
    """The assembled quad-core netlist (top.v, blocks.v), built when missing or stale: the CPU-only build, or with the GPU cluster (gpu=True)."""
    V = "5" if mem else "4"            # quad5: external memory behind AXI4 with instruction and data caches; quad4: on-chip RAM
    tail = ("-bp" if bp else "") + ("-hier" if hier else "") + ("-periph" if periph else "") + ("-post" if post else "") + ("-wfi" if wfi else "") + ("-wa" if wa else "") + ("-tlb32" if tlb32 else "") + ("-pmp" if pmp else "") + ("-ps2" if ps2 and periph else "")     # gshare predictors, L2/L3, GPIO/SPI/I2C (quad5 only)
    name = ("linux-quad-gpu" if gpu else "linux-quad") + ("-fp" if fp else "") + ("-mem" if mem else "") + tail
    sfx = ("" if gpu else "-nogpu") + ("-fp" if fp else "") + tail
    out = CACHE / name / "out"
    flat = CACHE / name / "flat"
    stamp = CACHE / name / "stamp"
    src = ROOT / "demos" / "quad-soc" / f"design-quad{V}{sfx}.json"
    core = ROOT / "demos" / "linux-soc" / ("design-core" + ("-mem" if mem else "") + ("-fp" if fp else "") + ("-bp" if bp else "") + ("-pmp" if pmp else "") + ("-sext" if ps2 and periph else "") + ".json")
    inputs = [src, core, ROOT / "demos" / "linux-soc" / "assemble.py", *(ROOT / "demos" / n for n in ("quad-soc/build_quad5.py", "quad-soc/build_quad.py", "quad-soc/memblocks.py", "linux-soc/build_core.py", "linux-soc/blocks.py")), *sorted((ROOT / "demos" / "linux-soc" / "rtl").glob("*.v")),
              *sorted((ROOT / "demos" / "quad-soc" / "rtl").glob("*.v")), *sorted((ROOT / "demos" / "linux-soc" / "rtl").glob("*.v"))]
    newest = max((f.stat().st_mtime for f in inputs if f.exists()), default=0) if all(f.exists() for f in (src, core)) else float("inf")     # a design not built yet: build
    if not rebuild and (out / "top.v").exists() and stamp.exists() and stamp.stat().st_mtime >= newest:
        return out
    print("building the SoC netlist from BARG's accepted blocks ...", flush=True)
    shutil.rmtree(CACHE / name, ignore_errors=True)
    flat.mkdir(parents=True)
    if fp:
        subprocess.run([sys.executable, str(ROOT / "demos" / "linux-soc" / "build_core.py"), *(["--mem"] if mem else []), "--fp", *(["--bp"] if bp else []), *(["--pmp"] if pmp else []), *(["--sext"] if ps2 and periph else [])], check=True, stdout=subprocess.DEVNULL, cwd=ROOT)
    off = lambda name, on: [] if on else [f"--no-{name}"]   # noqa: E731  (the final design has every feature on; a feature is left out only on request)
    subprocess.run([sys.executable, str(ROOT / "demos" / "quad-soc" / f"build_quad{V}.py"), *([] if gpu else ["--no-gpu"]), *(["--fp"] if fp else []),
                    *(["--bp"] if bp else []), *(["--hier"] if hier else []), *(["--periph"] if periph else []), *(["--post"] if post else []), *(["--tlb32"] if tlb32 else []),
                    *(["--wfi"] if wfi else []), *(["--wa"] if wa else []), *(["--pmp"] if pmp else []),
                    *(off("bp", bp) + off("hier", hier) + off("periph", periph) + off("post", post) + off("tlb32", tlb32) + off("wfi", wfi) + off("wa", wa) + off("pmp", pmp) + off("ps2", ps2) if V == "5" else [])], check=True, stdout=subprocess.DEVNULL, cwd=ROOT)
    for f, dst in ((f"design-quad{V}{sfx}.json", "design.json"), (f"copies{V}{sfx}.json", "copies.json"), (f"origid{V}{sfx}.json", "origid.json")):
        shutil.copy(ROOT / "demos" / "quad-soc" / f, flat / dst)
    if gpu:      # the GPU cluster is a nested IP: flatten it (as demos/quad-soc/tests/regress.sh does)
        subprocess.run(["node", str(ROOT / "packages" / "backend" / "dist" / "cli" / "ip.js"), "flatten", "--workspace", str(ROOT / "workspace"), "--design",
                        str(ROOT / "demos" / "quad-soc" / f"design-quad{V}{sfx}.json"), "--out", str(flat)], check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
        for f, dst in ((f"copies{V}{sfx}.json", "copies.json"), (f"origid{V}{sfx}.json", "origid.json")):
            shutil.copy(ROOT / "demos" / "quad-soc" / f, flat / dst)
    subprocess.run([sys.executable, str(ROOT / "demos" / "linux-soc" / "assemble.py"), str(flat / "design.json"), str(out)], check=True, cwd=ROOT,
                   stdout=subprocess.DEVNULL)
    stamp.write_text("ok")
    return out


def image_words(image: Path) -> Path:
    """The image as a text file of 32-bit words for $readmemh, kept next to the cache and reused while the image is unchanged."""
    hexf = CACHE / f"{image.stem}-{image.stat().st_size}-{int(image.stat().st_mtime)}.hex"
    if not hexf.exists():
        data = image.read_bytes()
        data += b"\0" * (-len(data) % 4)
        tmp = hexf.with_suffix(".tmp")
        tmp.write_text("".join(f"{w:08x}\n" for (w,) in struct.iter_unpack("<I", data)))
        tmp.rename(hexf)
    return hexf


def ckpt_pid(ckdir: Path, exe: Path) -> int:
    """The pid of the parked checkpoint copy in ckdir, or 0 when there is none (or its process is gone)."""
    try:
        pid = int((ckdir / "info").read_text().split()[0])
        os.kill(pid, 0)
        return pid if str(exe) in (Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace")) else 0
    except (OSError, ValueError, IndexError):
        return 0


def resume(ckdir: Path, a, extra: list, nxt) -> int:
    """Go on from the parked copy: it forks a run that uses this process's stdin and stdout (as /proc/<pid>/fd/N), the PS/2 input directory
    (BARG_PS2_DIR) and the frame directory; this process waits for that run to end and passes SIGTERM on."""
    me = os.getpid()
    pidf = ckdir / f"run-{me}.pid"
    pidf.unlink(missing_ok=True)
    frames = str(a.frames) if (a.gpu and a.frames) else "-"
    flags = 1 if a.pcs else 0
    print(f"resuming from the checkpoint {ckdir.name}" + (f"; this run parks the next one at cycle {nxt[0]}" if nxt else ""), flush=True)
    with open(ckdir / "ctl", "w") as f:
        f.write(f"run /proc/{me}/fd/0 /proc/{me}/fd/1 {os.environ.get('BARG_PS2_DIR') or '-'} {frames} {a.frame_every or 0} {pidf} {flags} {nxt[0] if nxt else 0} {nxt[1] if nxt else '-'}\n")
    for _ in range(200):
        if pidf.exists() and pidf.read_text().strip():
            break
        time.sleep(0.1)
    else:
        print("the checkpoint did not answer", file=sys.stderr)
        return 1
    cpid = int(pidf.read_text())

    def stop(_sig, _frm):
        try:
            os.killpg(cpid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        raise SystemExit(130)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while True:
        try:
            os.kill(cpid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.3)
    pidf.unlink(missing_ok=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", type=Path, default=DEFAULT_IMAGE, help="firmware image (default: the BusyBox shell with hard-float userland)")
    ap.add_argument("--keys", help='commands to type, separated by ";", each after the shell prompt; leaves after the last one finishes')
    ap.add_argument("--until", help="leave when the console has printed this text")
    ap.add_argument("--max-cycles", type=int, default=4_000_000_000)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--gpu", action="store_true", help="the SoC with the ten-core GPU cluster (about 4x slower to simulate); the shell's `gpu` command draws a scene on it")
    ap.add_argument("--no-fp", action="store_true", help="the integer-only cores (RV32IMAC) instead of the default RV32IMAFDC; needs an image built with FPU=n, e.g. --image ~/linux-work/pico/...")
    ap.add_argument("--mem", action="store_true", help="the memory-system SoC: 64 MB external memory behind AXI4 (30-cycle latency model) with per-core instruction and data caches")
    ap.add_argument("--no-hier", action="store_true", help="with --mem: leave out the L2 caches (one per pair of harts) and the L3")
    ap.add_argument("--no-bp", action="store_true", help="with --mem: cores without the gshare branch predictor")
    ap.add_argument("--no-periph", action="store_true", help="with --mem: leave out the GPIO, SPI master and I2C master in the peripheral window (0x1001_0000)")
    ap.add_argument("--stamp", action="store_true", help="print the cycle count at the end of every console line (to compare the speed of builds)")
    ap.add_argument("--ckpt-at", type=int, default=0, help="checkpoint: at this cycle (a multiple of 1024) the run parks a copy of the whole simulation; the next run with the same netlist, image and options resumes from the copy instead of booting again")
    ap.add_argument("--ckpt-chain", type=int, default=0, help="with --ckpt-at: a second, later checkpoint cycle; a run resumed from the first parks it, and later runs resume from the later one")
    ap.add_argument("--ckpt-new", type=int, default=0, help="with --ckpt-at: park one more checkpoint at this later cycle, taken by a run resumed from the latest existing one (use it to keep changes made by typing commands into the running system)")
    ap.add_argument("--no-resume", action="store_true", help="with --ckpt-at: ignore an existing checkpoint and boot from the start (the new run replaces it)")
    ap.add_argument("--ckpt-quit", action="store_true", help="with --ckpt-at: end the parked copy of this configuration (it holds about 100 MB of memory) and leave")
    ap.add_argument("--pcs", action="store_true", help="print the four harts' fetch addresses every 4M cycles (where is a silent boot?)")
    ap.add_argument("--pcfine", type=int, help="from this cycle on, print hart 0's fetch address every 4096 cycles")
    ap.add_argument("--dumpmem", help="FIRSTWORD,COUNT: at the end print these RAM words (word index from 0x8000_0000) on stderr, e.g. the kernel log buffer")
    ap.add_argument("--freeze123", action="store_true", help="experiment: harts 1-3 never run")
    ap.add_argument("--no-mem", action="store_true", help="the old on-chip RAM SoC (quad4) instead of the memory-system SoC (default: the memory-system SoC with every hardware feature)")
    for _f, _h in (("post", "posted plain stores"), ("tlb32", "32-entry TLBs"), ("wfi", "WFI halts the hart"), ("wa", "L3 write-allocate"), ("pmp", "sixteen PMP entries"), ("ps2", "the PS/2 keyboard and mouse ports with the 8-context PLIC")):
        ap.add_argument(f"--no-{_f}", action="store_true", help=f"leave out: {_h} (every hardware feature is on by default)")
    ap.add_argument("--post", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--tlb32", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--fast", action="store_true", help="the fastest boot of the real hardware: --mem --post --tlb32 --wfi --wa --pmp (the CLINT prescales the timebase by 16 in RTL; no testbench time tricks)")
    ap.add_argument("--uartmon", action="store_true", help="debug: report UART writes that stay asserted for two cycles or more")
    ap.add_argument("--tickdiv", type=int, default=1, help="simulation only: the timebase (mtime) advances once every N core cycles (default 1)")
    ap.add_argument("--warp", action="store_true", help="simulation only: while all four harts wait in WFI, skip the CLINT time to the next timer compare (idle waits cost no cycles)")
    ap.add_argument("--pmp", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--wa", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--wfi", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--frame-every", type=int, default=0, help="with --gpu --frames: also dump the video memory every N cycles (used by the GUI)")
    ap.add_argument("--frames", type=Path, help="with --gpu: at the end write GPU core 0's video memory as PNG into this directory")
    a = ap.parse_args()
    a.mem = not a.no_mem   # the final design is the default; --fast is kept as an alias
    # real hardware only: no testbench time tricks (--warp and --tickdiv stay available for experiments)
        # the timebase prescaler is hardware now (clint4_div: mtime counts once every 16 cycles); --tickdiv stays for experiments
    if not a.image.exists():
        sys.exit(f"no firmware image at {a.image} (build it with demos/linux-soc/sw/build.sh, or pass --image)")
    CACHE.mkdir(parents=True, exist_ok=True)
    net = netlist(a.rebuild, a.gpu, not a.no_fp, a.mem, a.mem and not a.no_bp, a.mem and not a.no_hier, a.mem and not a.no_periph, a.mem and not a.no_post, a.mem and not a.no_tlb32, a.mem and not a.no_wfi, a.mem and not a.no_wa, a.mem and not a.no_pmp, a.mem and not a.no_ps2)
    cpp = HERE / "console" / "host.cpp"
    if a.rebuild:
        shutil.rmtree(CACHE / "verilator", ignore_errors=True)
    print("preparing the simulator (first time: about a minute) ...", flush=True)
    exe = vlsim.build(net, HERE / "console" / "console_tb.v", includes=[HERE / "console"], extra=[cpp], defines=["GPU"] if a.gpu else [])
    hexf = image_words(a.image)
    env = dict(os.environ)
    if a.keys:
        env["BARG_KEYS"] = a.keys
        env["BARG_EXIT_AFTER_KEYS"] = "1"
    if a.until:
        env["BARG_UNTIL"] = a.until
    print(f"booting {a.image.name} on the quad-core SoC; Ctrl-A x leaves. The shell prompt appears after about two minutes.\n", flush=True)
    extra = (["+UARTMON"] if a.uartmon else []) + ([f"+TICKDIV={a.tickdiv}"] if a.tickdiv > 1 else []) + (["+WARP"] if a.warp else []) + (["+STAMP"] if a.stamp else []) + (["+PCS"] if a.pcs else []) + ([f"+PCFINE={a.pcfine}"] if a.pcfine else []) + (["+FREEZE123"] if a.freeze123 else []) + ([f"+DMBASE={a.dumpmem.split(',')[0]}", f"+DMCOUNT={a.dumpmem.split(',')[1]}"] if a.dumpmem else [])
    if a.gpu and a.frames:
        a.frames.mkdir(parents=True, exist_ok=True)
        extra.append(f"+FRAMES={a.frames}")
        if a.frame_every:
            extra.append(f"+FRAMEEVERY={a.frame_every}")
    if a.ckpt_at:
        key_args = [x for x in extra if not x.startswith(("+FRAMES=", "+FRAMEEVERY=", "+PCS"))]
        key = hashlib.sha1("|".join([str(exe), str(hexf), str(a.max_cycles), *key_args]).encode()).hexdigest()[:12]
        ckdir = CACHE / "ckpt" / f"{key}-{a.ckpt_at}"
        parked = ckpt_pid(ckdir, exe)
        chain_dir = (CACHE / "ckpt" / f"{key}-{a.ckpt_chain}") if a.ckpt_chain else None
        # every live checkpoint of this configuration, by cycle: a run resumes from the latest one
        live = sorted((int(p.name.rsplit("-", 1)[1]), p) for p in (CACHE / "ckpt").glob(f"{key}-*") if ckpt_pid(p, exe))
        if a.ckpt_quit:
            for _c, p in live:
                (p / "ctl").write_text("quit\n")
                print(f"checkpoint {p.name} ended")
            return 0
        if live and not a.no_resume:
            top_c, top_d = live[-1]
            nxt = None
            if a.ckpt_new and a.ckpt_new > top_c:        # park one more, later checkpoint from this run (the machine as it is then)
                nd = CACHE / "ckpt" / f"{key}-{a.ckpt_new}"
                shutil.rmtree(nd, ignore_errors=True)
                nd.mkdir(parents=True, exist_ok=True)
                nxt = (a.ckpt_new, nd)
            elif chain_dir is not None and top_c < a.ckpt_chain:
                shutil.rmtree(chain_dir, ignore_errors=True)
                chain_dir.mkdir(parents=True, exist_ok=True)
                nxt = (a.ckpt_chain, chain_dir)
            return resume(top_d, a, extra, nxt)
        if parked:
            (ckdir / "ctl").write_text("quit\n")
        shutil.rmtree(ckdir, ignore_errors=True)
        ckdir.mkdir(parents=True, exist_ok=True)
        env["BARG_CKPT_DIR"] = str(ckdir)
        if chain_dir is not None:      # this full run parks the later checkpoint as well
            shutil.rmtree(chain_dir, ignore_errors=True)
            chain_dir.mkdir(parents=True, exist_ok=True)
            env["BARG_CKPT_CHAIN"], env["BARG_CKPT_CHAIN_DIR"] = str(a.ckpt_chain), str(chain_dir)
        env["GLIBC_TUNABLES"] = "glibc.pthread.rseq=0"   # CRIU (3.16) cannot restore a process that registered rseq
        extra.append(f"+CKPT={a.ckpt_at}")
        print(f"this run parks a checkpoint at cycle {a.ckpt_at} ({ckdir.name}); the next run resumes from it", flush=True)
    pre = ["setarch", "x86_64", "-R"] if a.ckpt_at else []   # no address-space randomization: CRIU restores such a process reliably
    rc = subprocess.run([*pre, str(exe), f"+HEX={hexf}", f"+LIMIT={a.max_cycles}", *extra], env=env).returncode
    if a.gpu and a.frames and (a.frames / "f0_3.hex").exists():
        import gpu_png
        gpu_png.write_png(a.frames, a.frames / "gpu_frame.png")
        print(f"GPU core 0's frame: {a.frames / 'gpu_frame.png'}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
