/* gpu: render the scene of gpu_payload.h on the SoC's GPU, check the frame against the model's checksum, and save the frame
 * (320x240 RGB565, 38,400 words = 153,600 bytes) to /tmp/gpu.raw and to /dev/fb0 so that it can be sent to a PC through gzip.
 * The same sequence as `gpu` in init.c, run as a BusyBox-image program. A GPU read returns the value of the previous read, so every read is done twice. */
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/mman.h>
typedef uint32_t u32;
#include "../gpu_payload.h"
static u32 gpu_rd(volatile u32 *g, u32 off) { (void)g[off >> 2]; return g[off >> 2]; }
int main(void) {
  int fd = open("/dev/mem", O_RDWR | O_SYNC);
  if (fd < 0) { puts("gpu: cannot open /dev/mem"); return 1; }
  volatile u32 *g = (volatile u32 *)mmap(0, 0x200000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0x30000000);
  if (g == (volatile u32 *)MAP_FAILED) { puts("gpu: mmap of the GPU window failed"); return 1; }
  printf("gpu: loading %u words (scene %s)\n", (unsigned)GPU_N_WR, GPU_SCENE); fflush(stdout);
  for (u32 i = 0; i < GPU_N_WR; i++) g[GPU_WR[i][0] >> 2] = GPU_WR[i][1];
  for (u32 f = 0; f < GPU_N_FIL; f++) for (u32 j = 0; j < GPU_FIL[f][1]; j++) g[(GPU_FIL[f][0] >> 2) + j] = GPU_FIL[f][2];
  g[1] = GPU_START; g[2] = 0; g[0] = 1;
  u32 st = 0;
  for (u32 n = 0; n < 50000000u; n++) { st = gpu_rd(g, 0xC); if (st & 6) break; }
  printf("gpu: STATUS 0x%08x (%s)\n", (unsigned)st, st & 4 ? "error" : (st & 2 ? "done" : "timeout")); fflush(stdout);
  if (!(st & 2)) return 1;
  static u32 frame[GPU_FRAME_WORDS];
  u32 sum = 0;
  for (u32 k = 0; k < GPU_FRAME_WORDS; k++) { frame[k] = gpu_rd(g, GPU_FRAME_OFF + 4 * k); sum = sum * 31 + frame[k]; }
  printf("gpu: frame checksum 0x%08x %s\n", (unsigned)sum, sum == GPU_SUM_WANT ? "= the model's: the picture is right" : "!= the model's: wrong");
  int o = open("/tmp/gpu.raw", O_WRONLY | O_CREAT | O_TRUNC, 0644);
  if (o >= 0) { write(o, frame, sizeof frame); close(o); puts("gpu: frame saved to /tmp/gpu.raw"); }
  int fb = open("/dev/fb0", O_WRONLY);
  if (fb >= 0) { write(fb, frame, sizeof frame); close(fb); }
  return sum == GPU_SUM_WANT ? 0 : 2;
}
