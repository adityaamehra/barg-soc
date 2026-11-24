/* cursor: an arrow that follows the PS/2 mouse, drawn on /dev/fb0 (the BARG GPU framebuffer, 320x240 RGB565).
 * Reads the three-byte PS/2 packets of /dev/input/mice (button bits, dx, dy), keeps the pointer inside the screen and draws a 12x19 arrow with
 * pread/pwrite on the framebuffer (so the driver's dirty-row tracking sees every change). Under the arrow the old pixels are put back when it moves,
 * but only where the pixel still holds what the arrow drew (text the console wrote meanwhile is kept). The arrow is red while the left button is down.
 * Static binary, no libraries besides libc: riscv32-buildroot-linux-musl-gcc -Os -static cursor.c -o cursor */
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>

#define W 320
#define H 240
#define AW 12
#define AH 19
static const char *arrow[AH] = {
  "X           ", "XX          ", "X.X         ", "X..X        ", "X...X       ", "X....X      ", "X.....X     ", "X......X    ", "X.......X   ", "X........X  ",
  "X.........X ", "X......XXXXX", "X...X..X    ", "X..X X..X   ", "X.X  X..X   ", "XX    X..X  ", "X     X..X  ", "       X..X ", "       XXX  "};

static int fb;
static uint16_t under[AH][AW], drawn[AH][AW];
static int ox = -1, oy = -1;

static uint16_t rd(int x, int y) { uint16_t v = 0; pread(fb, &v, 2, ((off_t)y * W + x) * 2); return v; }
static void wr(int x, int y, uint16_t v) { pwrite(fb, &v, 2, ((off_t)y * W + x) * 2); }

static void erase(void) {
  if (ox < 0) return;
  for (int j = 0; j < AH; j++)
    for (int i = 0; i < AW; i++)
      if (arrow[j][i] != ' ' && ox + i < W && oy + j < H && rd(ox + i, oy + j) == drawn[j][i]) wr(ox + i, oy + j, under[j][i]);
  ox = -1;
}

static void draw(int x, int y, int down) {
  uint16_t fill = down ? 0xF800 : 0xFFFF;
  for (int j = 0; j < AH; j++)
    for (int i = 0; i < AW; i++) {
      char c = arrow[j][i];
      if (c == ' ' || x + i >= W || y + j >= H) continue;
      under[j][i] = rd(x + i, y + j);
      drawn[j][i] = c == 'X' ? 0x0000 : fill;
      wr(x + i, y + j, drawn[j][i]);
    }
  ox = x; oy = y;
}

int main(void) {
  fb = open("/dev/fb0", O_RDWR);
  int mice = open("/dev/input/mice", O_RDONLY);
  if (fb < 0 || mice < 0) { fputs("cursor: need /dev/fb0 and /dev/input/mice\n", stderr); return 1; }
  int x = W / 2, y = H / 2, down = 0;
  draw(x, y, down);
  unsigned char p[3];
  for (;;) {
    int got = 0;
    while (got < 3) { int n = read(mice, p + got, 3 - got); if (n <= 0) return 0; got += n; }
    if (!(p[0] & 8)) continue;                                   /* out of step: wait for a packet with bit 3 set */
    int dx = (int)p[1] - ((p[0] & 0x10) ? 256 : 0), dy = (int)p[2] - ((p[0] & 0x20) ? 256 : 0);
    x += dx; y -= dy;                                            /* PS/2 y grows upwards */
    x = x < 0 ? 0 : (x > W - 1 ? W - 1 : x);
    y = y < 0 ? 0 : (y > H - 1 ? H - 1 : y);
    down = p[0] & 1;
    erase();
    draw(x, y, down);
  }
}
