#!/usr/bin/env python3
"""Turn a firmware image (fw_payload.bin, linked for 0x8000_0000) into the words file the simulator loads with +HEX=: one 32-bit little-endian word per line.
    python3 linux/tools/bin2hex.py fw_payload.bin fw.hex"""
import struct, sys
data = open(sys.argv[1], "rb").read()
data += b"\0" * (-len(data) % 4)
open(sys.argv[2], "w").write("".join(f"{w:08x}\n" for (w,) in struct.iter_unpack("<I", data)))
print(f"{len(data)//4} words -> {sys.argv[2]}")
