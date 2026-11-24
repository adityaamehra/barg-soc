#!/usr/bin/env python3
"""Local GUI for the quad-core SoC simulation: starts run_linux.py (Verilator) and serves a web page with the GPU's video memory as a
live screen, the UART console as a terminal, and your keyboard and mouse sent to the simulated machine.

    python3 demos/linux-soc/gui/server.py [--port 8765] [--image FW.bin] [--frame-every CYCLES] [-- extra run_linux.py args]
    python3 demos/linux-soc/gui/server.py --serial /dev/ttyUSB3 [--baud 115200] --autostart     the console of the FPGA board instead of the simulator (no screen: the video pins are not on the page)
    then open http://127.0.0.1:8765/ in a browser on this machine.

Standard library only. The page and the simulator talk through this server: console bytes and frame notices go out as server-sent events,
keys and mouse events come in as POSTs. Keys (set-2 scan codes) and mouse packets are appended to <frames dir>/kbd.in and mouse.in, which the testbench's PS/2 device models read.
"""
import argparse, base64, json, os, signal, subprocess, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINUX = HERE.parent
sys.path.insert(0, str(LINUX))
import gpu_png  # noqa: E402

state = {"log": bytearray(), "frame": b"", "seq": -1, "cycles": 0, "t0": time.time(), "alive": False, "mouse": 0, "run": 0, "started": False}
sim = {"proc": None, "cmd": None, "fdir": None}
cv = threading.Condition()


def reader(proc, run):
    while True:
        b = os.read(proc.stdout.fileno(), 4096)
        if not b:
            break
        with cv:
            if state["run"] != run:
                return
            state["log"] += b
            cv.notify_all()
    with cv:
        if state["run"] == run:
            state["alive"] = False
            cv.notify_all()


def start_sim() -> str:
    with cv:
        if state["alive"]:
            return "already running"
        old = sim["proc"]
    if old and old.poll() is None:
        kill_group(old)
    fdir = sim["fdir"]
    for f in fdir.glob("*"):
        f.unlink()
    if sim.get("serial"):    # the FPGA board: the console is the board's USB serial port (115200 8N1), read by cat
        subprocess.run(["stty", "-F", sim["serial"], str(sim["baud"]), "raw", "-echo", "clocal", "-hupcl"], check=False)
    proc = subprocess.Popen(sim["cmd"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0, start_new_session=True, env={**os.environ, "BARG_PS2_DIR": str(fdir)})
    with cv:
        state.update(log=bytearray(), frame=b"", seq=-1, cycles=0, t0=time.time(), alive=True, started=True, run=state["run"] + 1)
        run = state["run"]
        sim["proc"] = proc
        cv.notify_all()
    threading.Thread(target=reader, args=(proc, run), daemon=True).start()
    return "started"


def kill_group(p):
    try:
        os.killpg(p.pid, signal.SIGTERM)   # run_linux.py and the simulator it started (this run's own process group)
    except ProcessLookupError:
        pass


def stop_sim() -> str:
    p = sim["proc"]
    if p and p.poll() is None:
        kill_group(p)
        return "stopped"
    return "not running"


def frame_watcher(d: Path):
    last = None
    while True:
        if not state["alive"]:
            last = None
            time.sleep(0.5)
            continue
        try:
            seq = (d / "seq").read_text().strip()
            if seq != last:
                last = seq
                png = d / "live.png"
                gpu_png.write_png(d, png)
                with cv:
                    state["frame"] = png.read_bytes()
                    state["cycles"] = int(seq)
                    state["seq"] += 1
                    cv.notify_all()
        except (FileNotFoundError, ValueError, IndexError):
            pass
        time.sleep(0.5)


# ---- screenshot of the board's framebuffer over the UART (--serial mode) ----
FB_W, FB_H = 320, 240
FB_BYTES = FB_W * FB_H * 2
B64_CHARS = 4 * ((FB_BYTES + 2) // 3)
LINE = 76
NLINES = (B64_CHARS + LINE - 1) // LINE
shot = {"busy": False, "msg": "idle", "abort": False}


def type_serial(text: str):
    """Type text into the board's UART one character at a time (the SoC's UART has a one-byte receive register)."""
    fd = os.open(sim["serial"], os.O_WRONLY | os.O_NOCTTY)
    for ch in text.encode():
        os.write(fd, bytes([ch]))
        time.sleep(0.06)
    os.close(fd)


def enable_ctrlc():
    """The board's shell has no controlling terminal (job control is off), so ^C would reach nobody: start a sub-shell that has one (cttyhack makes the console its controlling tty)."""
    if not sim.get("ctty"):
        type_serial("\n")
        type_serial("setsid cttyhack sh\n")
        sim["ctty"] = True
        time.sleep(6)


def send_ctrlc():
    shot["abort"] = True      # a running capture stops waiting
    fd = os.open(sim["serial"], os.O_WRONLY | os.O_NOCTTY)
    os.write(fd, b"\x03")    # ETX: the board's tty sends SIGINT to the running command
    os.close(fd)


def log_from(pos: int) -> bytes:
    with cv:
        return bytes(state["log"][pos:])


def png_rgb(w: int, h: int, rgb: bytes) -> bytes:
    import struct, zlib
    raw = b"".join(b"\x00" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def parse_lines(data: bytes, got: dict, nlines: int):
    import re
    for ln in data.replace(b"\r", b"").split(b"\n"):
        m = re.fullmatch(rb"F(\d+) ([A-Za-z0-9+/=]+)", ln.strip())
        if not m:
            continue
        k, payload = int(m.group(1)), m.group(2)
        ok = len(payload) == LINE if k < nlines else (0 < len(payload) <= LINE and len(payload) % 4 == 0)
        if 1 <= k <= nlines and ok:
            got[k] = payload


def wait_for(marker: bytes, pos: int, timeout: float) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if shot.get("abort"):
            raise RuntimeError("stopped by Ctrl+C")
        if marker in log_from(pos):
            return True
        time.sleep(1)
    return False


def screenshot(src: str = "/dev/fb0"):
    """The framebuffer is compressed on the board (gzip): the board's console sends only about 90 characters a second (its UART is driven by the kernel's timer), so the raw 205 KB would take 40 minutes."""
    import base64, gzip, re
    try:
        shot["abort"] = False
        shot["msg"] = "compressing the framebuffer on the board"
        pos = len(state["log"])
        pace = "j=0; while [ $j -lt 25 ]; do j=$((j+1)); done"
        type_serial("\n")
        type_serial("cat %s | gzip -c > /tmp/f.gz; base64 /tmp/f.gz | fold -w %d > /tmp/f.b64; echo FLINES $(wc -l < /tmp/f.b64); echo FREA\"\"DY\n" % (src, LINE))
        if not wait_for(b"FREADY", pos, 1800):
            shot["msg"] = "the board did not answer (is the shell prompt there?)"
            return
        m = re.search(rb"FLINES (\d+)", log_from(pos))
        if not m:
            shot["msg"] = "no line count from the board"
            return
        nlines = int(m.group(1))
        pos = len(state["log"])
        type_serial("i=1; while read l; do echo \"F$i $l\"; i=$((i+1)); %s; done < /tmp/f.b64; echo FE\"\"ND\n" % pace)
        got = {}
        for rnd in range(7):
            shot["msg"] = "round %d: waiting for the lines (%d of %d good)" % (rnd, len(got), nlines)
            if not wait_for(b"FEND", pos, 1800):
                shot["msg"] = "timed out waiting for the board"
                break
            parse_lines(log_from(pos), got, nlines)
            missing = [k for k in range(1, nlines + 1) if k not in got]
            if not missing:
                break
            pos = len(state["log"])
            type_serial("for k in %s; do echo \"F$k $(sed -n ${k}p /tmp/f.b64)\"; %s; done; echo FE\"\"ND\n" % (" ".join(map(str, missing[:40])), pace))
        if len(got) < nlines:
            shot["msg"] = "incomplete: %d of %d lines arrived" % (len(got), nlines)
            return
        raw = gzip.decompress(base64.b64decode(b"".join(got[k] for k in range(1, nlines + 1))))
        raw = raw[:FB_BYTES].ljust(FB_BYTES, b"\0")
        rgb = bytearray()
        for i in range(0, FB_BYTES, 2):
            v = raw[i] | (raw[i + 1] << 8)
            rgb += bytes(((v >> 11) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31))
        png = png_rgb(FB_W, FB_H, bytes(rgb))
        (sim["fdir"] / "live.png").write_bytes(png)
        with cv:
            state["frame"] = png
            state["seq"] += 1
            cv.notify_all()
        shot["msg"] = "done: %d lines, %d bytes compressed" % (nlines, nlines * LINE)
    except Exception as e:  # noqa: BLE001
        shot["msg"] = "failed: %s" % e
    finally:
        shot["busy"] = False


def make_handler(fdir: Path):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, ctype, body, extra=()):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in extra:
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                return self.send(200, "text/html; charset=utf-8", (HERE / "index.html").read_bytes())
            if self.path.startswith("/frame.png"):
                with cv:
                    f = state["frame"]
                return self.send(200, "image/png", f) if f else self.send(404, "text/plain", b"no frame yet")
            if self.path == "/shot":
                return self.send(200, "application/json", json.dumps(shot).encode())
            if self.path == "/status":
                with cv:
                    s = {"alive": state["alive"], "started": state["started"], "run": state["run"], "cycles": state["cycles"], "seq": state["seq"], "up": round(time.time() - state["t0"]), "bytes": len(state["log"])}
                return self.send(200, "application/json", json.dumps(s).encode())
            if self.path.startswith("/events"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                pos, seq, run, ended = 0, -1, -1, False
                try:
                    while True:
                        with cv:
                            cv.wait_for(lambda: state["run"] != run or len(state["log"]) > pos or state["seq"] != seq or (not state["alive"] and not ended), timeout=15)
                            if state["run"] != run:
                                run, pos, seq, ended = state["run"], 0, -1, False
                                self.wfile.write(b"event: reset\ndata: %d\n\n" % run)
                            chunk, pos = bytes(state["log"][pos:]), len(state["log"])
                            newf, seq, cyc, alive = state["seq"] != seq and state["seq"] >= 0, state["seq"], state["cycles"], state["alive"]
                        if chunk:
                            self.wfile.write(b"event: con\ndata: " + base64.b64encode(chunk) + b"\n\n")
                        if newf:
                            self.wfile.write(b"event: frame\ndata: %d\n\n" % cyc)
                        if not chunk and not newf:
                            self.wfile.write(b": keepalive\n\n")
                        if not alive and not chunk and state["started"] and not ended:
                            ended = True
                            self.wfile.write(b"event: end\ndata: 0\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return
            self.send(404, "text/plain", b"not found")

        def do_POST(self):
            n = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(n)
            if self.path == "/start":
                return self.send(200, "text/plain", start_sim().encode())
            if self.path == "/ctrlc":
                if not sim.get("serial"):
                    return self.send(400, "text/plain", b"Ctrl+C works in --serial mode only")
                send_ctrlc()
                return self.send(200, "text/plain", b"sent ^C")
            if self.path == "/ctrlc-enable":
                threading.Thread(target=enable_ctrlc, daemon=True).start()
                return self.send(200, "text/plain", b"enabling")
            if self.path.split("?")[0] == "/screenshot":
                if not sim.get("serial"):
                    return self.send(400, "text/plain", b"screenshots work in --serial mode only")
                if shot["busy"]:
                    return self.send(200, "text/plain", b"already running")
                import re as _re, urllib.parse as _up
                q = _up.parse_qs(_up.urlparse(self.path).query)
                src = q.get("src", ["/dev/fb0"])[0]
                if not _re.fullmatch(r"/[A-Za-z0-9_./-]{1,60}", src):
                    return self.send(400, "text/plain", b"bad src")
                shot["busy"] = True
                threading.Thread(target=screenshot, args=(src,), daemon=True).start()
                return self.send(200, "text/plain", b"started")
            if self.path == "/stop":
                return self.send(200, "text/plain", stop_sim().encode())
            if self.path == "/key":
                try:
                    if sim.get("serial"):    # keys typed in the page go to the board's UART
                        fd = os.open(sim["serial"], os.O_WRONLY | os.O_NOCTTY)
                        for ch in body:      # the SoC's UART has a one-byte receive register and the kernel polls it: one character at a time
                            os.write(fd, bytes([ch]))
                            time.sleep(0.06)
                        os.close(fd)
                        return self.send(200, "text/plain", b"ok")
                    sim["proc"].stdin.write(body.replace(b"\x01x", b"\x01a"))   # leaving the simulator is the Stop button's job
                    sim["proc"].stdin.flush()
                except (BrokenPipeError, ValueError, AttributeError):
                    return self.send(410, "text/plain", b"simulator is not running")
                return self.send(200, "text/plain", b"ok")
            if self.path == "/ps2type":   # plain text typed on the PS/2 keyboard (the page's text box): \n is Enter
                import type_ps2
                txt = json.loads(body or b"{}").get("text", "")
                with open(fdir / "kbd.in", "ab") as f:
                    f.write(bytes(type_ps2.codes(txt)))
                return self.send(200, "text/plain", b"ok")
            if self.path == "/ps2k":     # PS/2 keyboard: a JSON list of scan-code bytes (set 2), appended to the file the testbench reads
                with open(fdir / "kbd.in", "ab") as f:
                    f.write(bytes(int(b) & 255 for b in json.loads(body or b"[]")))
                return self.send(200, "text/plain", b"ok")
            if self.path == "/mouse":    # {"dx": .., "dy": .., "b": mask (bit 0 left, 1 middle, 2 right of the browser)}: three-byte PS/2 packets
                ev = json.loads(body or b"{}")
                out = bytearray()
                dx, dy, b = int(ev.get("dx", 0)), -int(ev.get("dy", 0)), int(ev.get("b", 0))   # PS/2 y grows upwards
                btn = (1 if b & 1 else 0) | (2 if b & 4 else 0) | (4 if b & 2 else 0)
                while True:
                    sx, sy = max(-255, min(255, dx)), max(-255, min(255, dy))
                    out += bytes([0x08 | btn | (0x10 if sx < 0 else 0) | (0x20 if sy < 0 else 0), sx & 255, sy & 255])
                    dx, dy = dx - sx, dy - sy
                    if not dx and not dy:
                        break
                with open(fdir / "mouse.in", "ab") as f:
                    f.write(out)
                state["mouse"] += 1
                return self.send(200, "text/plain", b"ok")
            self.send(404, "text/plain", b"not found")
    return H


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--image", default=str(Path.home() / "linux-work/pico-ui/sbi/platform/generic/firmware/fw_payload.bin"))
    ap.add_argument("--frame-every", type=int, default=4194304, help="cycles between screen updates (default 4194304, about 10 s of simulation)")
    ap.add_argument("--frames-dir", default=None)
    ap.add_argument("--ckpt-at", type=int, default=190000128, help="checkpoint cycle (a multiple of 1024): the first Start boots and parks a copy of the whole simulation here; later Starts resume from it in seconds (0 turns it off)")
    ap.add_argument("--ckpt-chain", type=int, default=335000576, help="a later checkpoint cycle (a multiple of 1024), taken by the first resumed run at about the shell prompt; 0 turns it off")
    ap.add_argument("--ckpt-new", type=int, default=0, help="park one more checkpoint at this cycle when resuming (keeps what you typed into the running Linux)")
    ap.add_argument("--serial", default=None, help="show the console of the FPGA board on this serial port (for example /dev/ttyUSB3) instead of running the simulator")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--no-sim", action="store_true", help="serve the page only (layout work)")
    ap.add_argument("--autostart", action="store_true", help="start the simulation right away instead of waiting for the Start button")
    a, rest = ap.parse_known_args()
    fdir = Path(a.frames_dir or tempfile.mkdtemp(prefix="barg-gui-"))
    fdir.mkdir(parents=True, exist_ok=True)
    sim["fdir"] = fdir
    if a.serial:
        sim.update(serial=a.serial, baud=a.baud)
        sim["cmd"] = ["cat", a.serial]
    elif a.no_sim:
        sim["cmd"] = ["cat"]
    else:
        sim["cmd"] = [sys.executable, "-u", str(LINUX / "run_linux.py"), "--gpu", "--frames", str(fdir), "--frame-every", str(a.frame_every), "--image", a.image, *(["--ckpt-at", str(a.ckpt_at)] if a.ckpt_at else []), *(["--ckpt-chain", str(a.ckpt_chain)] if a.ckpt_at and a.ckpt_chain else []), *(["--ckpt-new", str(a.ckpt_new)] if a.ckpt_at and a.ckpt_new else []), *[r for r in rest if r != "--"]]
    threading.Thread(target=frame_watcher, args=(fdir,), daemon=True).start()
    if a.autostart:
        start_sim()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(fdir))
    print(f"open http://127.0.0.1:{a.port}/   (frames in {fdir}; Ctrl-C stops the simulator)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_sim()
    return 0


if __name__ == "__main__":
    sys.exit(main())
