#!/usr/bin/env python3
"""Type text on the simulated PS/2 keyboard through the GUI server:  type_ps2.py [--port 8793] 'ls -l\\n' ...   (\\n is Enter)"""
import argparse, json, urllib.request
L = {c: s for c, s in zip("abcdefghijklmnopqrstuvwxyz", [0x1C,0x32,0x21,0x23,0x24,0x2B,0x34,0x33,0x43,0x3B,0x42,0x4B,0x3A,0x31,0x44,0x4D,0x15,0x2D,0x1B,0x2C,0x3C,0x2A,0x1D,0x22,0x35,0x1A])}
D = {c: s for c, s in zip("1234567890", [0x16,0x1E,0x26,0x25,0x2E,0x36,0x3D,0x3E,0x46,0x45])}
P = {" ": 0x29, "\n": 0x5A, "-": 0x4E, "=": 0x55, "[": 0x54, "]": 0x5B, "\\": 0x5D, ";": 0x4C, "'": 0x52, "`": 0x0E, ",": 0x41, ".": 0x49, "/": 0x4A, "\t": 0x0D}
SH = {"!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8", "(": "9", ")": "0", "_": "-", "+": "=", "{": "[", "}": "]", "|": "\\", ":": ";", '"': "'", "<": ",", ">": ".", "?": "/", "~": "`"}
LSHIFT = 0x12


def codes(text):
    out = []
    for ch in text:
        shift = ch.isupper() or ch in SH
        base = SH.get(ch, ch.lower())
        sc = L.get(base) or D.get(base) or P.get(base)
        if sc is None:
            continue
        if shift:
            out += [LSHIFT]
        out += [sc, 0xF0, sc]
        if shift:
            out += [0xF0, LSHIFT]
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8793)
    ap.add_argument("text", nargs="+")
    a = ap.parse_args()
    for t in a.text:
        t = t.replace("\\n", "\n")
        urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{a.port}/ps2k", data=json.dumps(codes(t)).encode(), method="POST")).read()
        print("typed", repr(t))
