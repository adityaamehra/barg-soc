"""Turns the video-memory dumps of console_tb.v (+FRAMES=dir: f0_0.hex .. f0_3.hex, four interleaved banks of RGB565 pixels) into a PNG."""
import struct, sys, zlib
from pathlib import Path

W, H = 320, 240


def png(path: Path, w: int, h: int, rgb: bytes) -> None:
    raw = b"".join(b"\0" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def frame_from_dumps(d: Path) -> list[int]:
    banks = [[int(x, 16) for line in (d / f"f0_{b}.hex").read_text().splitlines() if not line.startswith(("//", "@")) for x in line.split()] for b in range(4)]
    return [banks[p % 4][p // 4] for p in range(W * H)]


def write_png(d: Path, out: Path) -> int:
    px = frame_from_dumps(d)
    rgb = bytearray()
    for p in px:
        rgb += bytes(((p >> 11 & 31) * 255 // 31, (p >> 5 & 63) * 255 // 63, (p & 31) * 255 // 31))
    png(out, W, H, bytes(rgb))
    return sum(1 for p in px if p != px[0])


if __name__ == "__main__":
    n = write_png(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"{sys.argv[2]}: {n} pixels differ from the corner colour")
