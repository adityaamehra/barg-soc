/* pico init for Linux on the BARG SoC: PID 1 and a tiny shell, raw RV32 Linux syscalls, no libc.
 * Build: riscv-none-elf-gcc -march=rv32imac_zicsr -mabi=ilp32 -O2 -ffreestanding -nostdlib -static -o init init.c
 * Commands: help, uname, echo, ls [dir], cat <file>, free, uptime, ps, fork, mem, gpu, poweroff.
 * gpu: draws a scene on the SoC's GPU (needs gpu_payload.h from gen_gpu_payload.py and a GPU build of the SoC). */
typedef unsigned int u32;
typedef int s32;
typedef unsigned long long u64;

static long sys6(long n, long a, long b, long c, long d, long e, long f) {
  register long a0 asm("a0") = a, a1 asm("a1") = b, a2 asm("a2") = c, a3 asm("a3") = d, a4 asm("a4") = e, a5 asm("a5") = f;
  register long a7 asm("a7") = n;
  asm volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a3), "r"(a4), "r"(a5), "r"(a7) : "memory");
  return a0;
}
#define SYS(n, a, b, c) sys6(n, (long)(a), (long)(b), (long)(c), 0, 0, 0)
enum { S_GETDENTS = 61, S_READ = 63, S_WRITE = 64, S_OPENAT = 56, S_CLOSE = 57, S_EXIT = 93, S_UNAME = 160, S_SYSINFO = 179,
       S_GETPID = 172, S_CLONE = 220, S_WAIT4 = 260, S_MOUNT = 40, S_MKDIRAT = 34, S_REBOOT = 142, S_CLOCK_GETTIME64 = 403,
       S_BRK = 214, S_MMAP2 = 222, S_EXECVE = 221 };
#define AT_FDCWD (-100)

void *memset(void *d, int c, unsigned n) { unsigned char *p = d; while (n--) *p++ = (unsigned char)c; return d; }
void *memcpy(void *d, const void *s, unsigned n) { unsigned char *p = d; const unsigned char *q = s; while (n--) *p++ = *q++; return d; }
static unsigned slen(const char *s) { unsigned n = 0; while (s[n]) n++; return n; }
static int seq(const char *a, const char *b) { while (*a && *a == *b) { a++; b++; } return *a == *b; }
static void puts_(const char *s) { SYS(S_WRITE, 1, s, slen(s)); }
static void putu(u64 v) { char b[24]; int i = 23; b[i] = 0; do { b[--i] = (char)('0' + v % 10); v /= 10; } while (v); puts_(b + i); }
static void cat(const char *path) {
  char buf[256]; long fd = sys6(S_OPENAT, AT_FDCWD, (long)path, 0, 0, 0, 0), n;
  if (fd < 0) { puts_("cat: cannot open "); puts_(path); puts_("\n"); return; }
  while ((n = SYS(S_READ, fd, buf, sizeof buf)) > 0) SYS(S_WRITE, 1, buf, n);
  SYS(S_CLOSE, fd, 0, 0);
}
static void ls(const char *path) {
  char buf[512]; long fd = sys6(S_OPENAT, AT_FDCWD, (long)path, 0x10000 /* O_DIRECTORY */, 0, 0, 0), n;
  if (fd < 0) { puts_("ls: cannot open "); puts_(path); puts_("\n"); return; }
  while ((n = SYS(S_GETDENTS, fd, buf, sizeof buf)) > 0)
    for (long off = 0; off < n;) {
      unsigned short reclen = *(unsigned short *)(buf + off + 16);
      puts_(buf + off + 19); puts_("  ");
      off += reclen;
    }
  puts_("\n");
  SYS(S_CLOSE, fd, 0, 0);
}
struct sysinfo_ { s32 uptime; u32 loads[3], totalram, freeram, sharedram, bufferram, totalswap, freeswap; unsigned short procs, pad;
                  u32 totalhigh, freehigh, mem_unit; char f[8]; };
/* touch n pages of fresh heap: each first touch is a page fault the kernel serves through the MMU */
static void mem_test(void) {
  u32 base = (u32)SYS(S_BRK, 0, 0, 0), want = base + 64 * 4096;
  if ((u32)SYS(S_BRK, want, 0, 0) != want) { puts_("mem: brk failed\n"); return; }
  for (u32 p = base; p < want; p += 4096) *(volatile u32 *)p = p ^ 0x5a5a5a5a;
  u32 bad = 0;
  for (u32 p = base; p < want; p += 4096) bad += *(volatile u32 *)p != (p ^ 0x5a5a5a5a);
  puts_("mem: 64 pages touched, "); putu(bad); puts_(" wrong\n");
}
#if __has_include("gpu_payload.h")
#include "gpu_payload.h"
static void puthex(u32 v) { char b[9]; for (int i = 7; i >= 0; i--) { b[i] = "0123456789abcdef"[v & 15]; v >>= 4; } b[8] = 0; puts_("0x"); puts_(b); }
/* Linux userspace drives the GPU through /dev/mem: map its 2 MB window (physical 0x30000000), load the rasteriser and the scene, start, wait for
 * STATUS, read the frame back from video memory and check it against the frame model's checksum. A GPU read returns the value of the previous
 * read, so every read is done twice. */
static u32 gpu_rd(volatile u32 *g, u32 off) { (void)g[off >> 2]; return g[off >> 2]; }
static void gpu_cmd(void) {
  long fd = sys6(S_OPENAT, AT_FDCWD, (long)"/dev/mem", 0x101002 /* O_RDWR | O_SYNC */, 0, 0, 0);
  if (fd < 0) { puts_("gpu: cannot open /dev/mem\n"); return; }
  long m = sys6(S_MMAP2, 0, 0x200000, 3 /* PROT_READ | PROT_WRITE */, 1 /* MAP_SHARED */, fd, 0x30000000 >> 12);
  if (m < 0 && m > -4096) { puts_("gpu: mmap of the GPU window failed\n"); return; }
  volatile u32 *g = (volatile u32 *)m;
  puts_("gpu: window mapped, loading "); putu(GPU_N_WR); puts_(" words (scene " GPU_SCENE ")\n");
  for (u32 i = 0; i < GPU_N_WR; i++) g[GPU_WR[i][0] >> 2] = GPU_WR[i][1];
  for (u32 f = 0; f < GPU_N_FIL; f++) for (u32 j = 0; j < GPU_FIL[f][1]; j++) g[(GPU_FIL[f][0] >> 2) + j] = GPU_FIL[f][2];
  g[1] = GPU_START; g[2] = 0; g[0] = 1;                       /* START_PC, KARG, CTRL = 1 */
  puts_("gpu: started, waiting\n");
  u32 st = 0;
  for (u32 n = 0; n < 50000000u; n++) { st = gpu_rd(g, 0xC); if (st & 6) break; }
  puts_("gpu: STATUS "); puthex(st); puts_(st & 4 ? " (error)\n" : (st & 2 ? " (done)\n" : " (timeout)\n"));
  if (!(st & 2)) return;
  u32 sum = 0;
  for (u32 k = 0; k < GPU_FRAME_WORDS; k++) sum = sum * 31 + gpu_rd(g, GPU_FRAME_OFF + 4 * k);
  puts_("gpu: frame checksum "); puthex(sum); puts_(sum == GPU_SUM_WANT ? " = the model's: the picture is right\n" : " != the model's "); if (sum != GPU_SUM_WANT) { puthex(GPU_SUM_WANT); puts_("\n"); }
}
#else
static void gpu_cmd(void) { puts_("gpu: not built in (no gpu_payload.h)\n"); }
#endif
static void fork_test(void) {
  volatile u32 shared = 1;
  long pid = sys6(S_CLONE, 17 /* SIGCHLD */, 0, 0, 0, 0, 0);
  if (pid == 0) { shared = 2; puts_("child: pid "); putu((u64)SYS(S_GETPID, 0, 0, 0)); puts_(", my copy of x = "); putu(shared); puts_("\n"); SYS(S_EXIT, 7, 0, 0); }
  int status = 0;
  sys6(S_WAIT4, pid, (long)&status, 0, 0, 0, 0);
  puts_("parent: child "); putu((u64)pid); puts_(" exited with "); putu((u32)(status >> 8) & 0xff);
  puts_(", my x = "); putu(shared); puts_(" (copy-on-write kept it)\n");
}
/* x <program> [args]: fork and exec an external program (for example BusyBox from the initramfs), print how it ended or why the exec failed */
static void putneg(long v) { if (v < 0) { puts_("-"); putu((u64)(-v)); } else putu((u64)v); }
static void exec_cmd(char **argv) {
  static char *envp[] = { "PATH=/bin:/sbin", "HOME=/", 0 };
  long pid = sys6(S_CLONE, 17 /* SIGCHLD */, 0, 0, 0, 0, 0);
  if (pid == 0) { long r = sys6(S_EXECVE, (long)argv[0], (long)argv, (long)envp, 0, 0, 0); puts_("x: exec failed, errno "); putneg(-r); puts_("\n"); SYS(S_EXIT, 127, 0, 0); }
  int status = 0;
  sys6(S_WAIT4, pid, (long)&status, 0, 0, 0, 0);
  puts_("x: exit status "); putu((u32)(status >> 8) & 0xff); puts_(status & 0x7f ? ", killed by signal " : "\n"); if (status & 0x7f) { putu((u32)(status & 0x7f)); puts_("\n"); }
}
/* xl <n> <program> [args]: exec the program n times in a row; prints "." for a good run, "E<errno>" when exec failed, "S<status>" for another exit status */
static void exec_loop(u32 n, char **argv) {
  static char *envp[] = { "PATH=/bin:/sbin", "HOME=/", 0 };
  u32 bad = 0;
  for (u32 i = 0; i < n; i++) {
    int fds[2]; (void)fds;
    long pid = sys6(S_CLONE, 17, 0, 0, 0, 0, 0);
    if (pid == 0) { long r = sys6(S_EXECVE, (long)argv[0], (long)argv, (long)envp, 0, 0, 0); SYS(S_EXIT, 100 + (int)(-r), 0, 0); }
    int status = 0; sys6(S_WAIT4, pid, (long)&status, 0, 0, 0, 0);
    u32 code = (u32)(status >> 8) & 0xff;
    if (code == 0) puts_("."); else if (code >= 100) { puts_("E"); putu(code - 100); bad++; } else { puts_("S"); putu(code); bad++; }
  }
  puts_("\nxl: "); putu(n); puts_(" runs, "); putu(bad); puts_(" bad\n");
}
static void run(char *line) {
  char *argv[8]; int argc = 0;
  for (char *p = line; *p && argc < 8;) { while (*p == ' ') *p++ = 0; if (!*p) break; argv[argc++] = p; while (*p && *p != ' ') p++; }
  if (argc == 0) return;
  const char *c = argv[0];
  if (seq(c, "help")) puts_("help uname echo ls cat free uptime ps fork mem gpu x poweroff\n");
  else if (seq(c, "echo")) { for (int i = 1; i < argc; i++) { puts_(argv[i]); puts_(i + 1 < argc ? " " : ""); } puts_("\n"); }
  else if (seq(c, "uname")) { char u[6 * 65]; SYS(S_UNAME, u, 0, 0); for (int i = 0; i < 5; i++) { puts_(u + 65 * i); puts_(" "); } puts_("\n"); }
  else if (seq(c, "ls")) ls(argc > 1 ? argv[1] : "/");
  else if (seq(c, "cat")) { if (argc > 1) cat(argv[1]); }
  else if (seq(c, "free") || seq(c, "uptime")) {
    struct sysinfo_ si; SYS(S_SYSINFO, &si, 0, 0);
    if (seq(c, "free")) { puts_("total "); putu((u64)si.totalram * si.mem_unit / 1024); puts_(" KB, free "); putu((u64)si.freeram * si.mem_unit / 1024); puts_(" KB\n"); }
    else { puts_("up "); putu((u32)si.uptime); puts_(" s, "); putu(si.procs); puts_(" processes\n"); }
  }
  else if (seq(c, "ps")) ls("/proc");
  else if (seq(c, "fork")) fork_test();
  else if (seq(c, "mem")) mem_test();
  else if (seq(c, "gpu")) gpu_cmd();
  else if (seq(c, "xl")) { if (argc > 2) { u32 n = 0; for (const char *q = argv[1]; *q; q++) n = n * 10 + (u32)(*q - '0'); exec_loop(n, argv + 2); } }
  else if (seq(c, "x")) { if (argc > 1) exec_cmd(argv + 1); }
  else if (seq(c, "poweroff")) sys6(S_REBOOT, 0xfee1dead, 672274793, 0x4321fedc, 0, 0, 0);
  else { puts_(c); puts_(": unknown command (help)\n"); }
}
void main_(void) {
  SYS(S_MKDIRAT, AT_FDCWD, "/proc", 0755);
  sys6(S_MOUNT, (long)"proc", (long)"/proc", (long)"proc", 0, 0, 0);
  puts_("\npico init: Linux userspace on the BARG SoC (MMU on). Type help.\n");
  char line[128];
  for (;;) {
    puts_("barg# ");
    int n = 0;
    for (;;) {
      char ch; long r = SYS(S_READ, 0, &ch, 1);
      if (r <= 0) continue;
      if (ch == '\r' || ch == '\n') { puts_("\n"); break; }
      if ((ch == 8 || ch == 127) && n > 0) { n--; puts_("\b \b"); continue; }
      if (n < 127) { line[n++] = ch; SYS(S_WRITE, 1, &ch, 1); }
    }
    line[n] = 0;
    run(line);
  }
}
asm(".globl _start\n_start:\n  .option push\n  .option norelax\n  la gp, __global_pointer$\n  .option pop\n  andi sp, sp, -16\n  call main_\n1: j 1b\n");
