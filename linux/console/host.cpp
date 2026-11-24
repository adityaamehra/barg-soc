// The host side of the SoC's console: connects the terminal to the UART of the simulated SoC (called from console_tb.v through DPI-C).
//   interactive: your keystrokes go to the UART receiver, the UART transmitter's bytes go to your terminal. The terminal is put in raw mode, so
//                Ctrl-C and the like go to the guest. Ctrl-A x leaves the simulator, Ctrl-A a sends a Ctrl-A, Ctrl-A h prints this help.
//   scripted:    BARG_KEYS="cmd1;cmd2" types each command after the shell prompt "barg# " has appeared (so a command is never typed into a busy shell);
//                BARG_EXIT_AFTER_KEYS=1 leaves after the last command has finished. BARG_UNTIL="text" leaves as soon as the console has printed the text.
#include "svdpi.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <poll.h>
#include <termios.h>
#include <unistd.h>
#include <csignal>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>

static struct termios g_saved;
static bool g_raw = false, g_tty = false, g_quit = false, g_ctrl_a = false, g_script = false, g_exit_after = false;
static bool g_prompt_seen = false, g_wait_final = false, g_last_cr = false;
static std::string g_tail, g_until, g_cur;
static std::vector<std::string> g_lines;
static size_t g_next_line = 0, g_cur_pos = 0;

static void restore() { if (g_raw) { tcsetattr(0, TCSANOW, &g_saved); g_raw = false; } }
static void on_term(int) { restore(); _exit(130); }

extern "C" {

static void do_init() {
  g_tty = isatty(0);
  if (const char* k = getenv("BARG_KEYS")) {
    std::string s(k), cur;
    for (char c : s) { if (c == ';') { g_lines.push_back(cur); cur.clear(); } else cur += c; }
    if (!cur.empty()) g_lines.push_back(cur);
    g_script = !g_lines.empty();
  }
  if (const char* u = getenv("BARG_UNTIL")) g_until = u;
  g_exit_after = getenv("BARG_EXIT_AFTER_KEYS") != nullptr;
  if (g_tty && !g_script) {
    tcgetattr(0, &g_saved);
    struct termios raw = g_saved;
    cfmakeraw(&raw);
    tcsetattr(0, TCSANOW, &raw);
    g_raw = true;
    atexit(restore);
    signal(SIGTERM, on_term);
  }
}

void host_init() { do_init(); }

int host_getc() {
  if (g_quit) return -1;
  if (g_script) {
    if (g_cur_pos < g_cur.size()) return (unsigned char)g_cur[g_cur_pos++];
    if (g_next_line < g_lines.size() && g_prompt_seen) {
      g_cur = g_lines[g_next_line++] + "\r"; g_cur_pos = 0; g_prompt_seen = false;
      if (g_next_line == g_lines.size()) g_wait_final = true;
      return (unsigned char)g_cur[g_cur_pos++];
    }
    return -1;
  }
  struct pollfd p = {0, POLLIN, 0};
  if (poll(&p, 1, 0) <= 0) return -1;
  unsigned char c;
  if (read(0, &c, 1) != 1) return -1;
  if (g_ctrl_a) {
    g_ctrl_a = false;
    if (c == 'x') { g_quit = true; return -1; }
    if (c == 'a') return 1;
    if (c == 'h') { fputs("\r\n[Ctrl-A x: leave the simulator, Ctrl-A a: send Ctrl-A]\r\n", stdout); fflush(stdout); }
    return -1;
  }
  if (c == 1) { g_ctrl_a = true; return -1; }
  return c;
}

void host_putc(int c) {
  char ch = (char)c;
  if (ch == '\n' && !g_last_cr) fputc('\r', stdout);   // the guest may send a bare newline
  fputc(ch, stdout);
  g_last_cr = (ch == '\r');
  if (ch == '\n' || ch == ' ' || (g_tail.size() % 32) == 0) fflush(stdout);
  g_tail += ch;
  if (g_tail.size() > 512) g_tail.erase(0, 256);
  if (g_tail.size() >= 6 && g_tail.compare(g_tail.size() - 6, 6, "barg# ") == 0) {
    g_prompt_seen = true;
    if (g_wait_final && g_exit_after) g_quit = true;
  }
  if (!g_until.empty() && g_tail.find(g_until) != std::string::npos) g_quit = true;
}

int host_quit() { return g_quit ? 1 : 0; }

// bytes for the simulated PS/2 devices: <BARG_PS2_DIR>/kbd.in (dev 0) and mouse.in (dev 1), appended to by the GUI server; one new byte per call
static long g_ps2_pos[2] = {0, 0};
int host_ps2_byte(int dev) {
  long* pos = g_ps2_pos;
  const char* d = getenv("BARG_PS2_DIR");
  if (!d || dev < 0 || dev > 1) return -1;
  std::string p = std::string(d) + (dev ? "/mouse.in" : "/kbd.in");
  FILE* f = fopen(p.c_str(), "rb");
  if (!f) return -1;
  fseek(f, pos[dev], SEEK_SET);
  int c = fgetc(f);
  fclose(f);
  if (c == EOF) return -1;
  pos[dev]++;
  return c;
}

// ---- checkpoint by fork. With BARG_CKPT_DIR set, host_checkpoint() (called by the testbench at the +CKPT cycle) forks: the original process goes on
// with the run; the copy becomes a parked "master", in its own session, that holds the exact state of the whole simulation (the model, the RAM, the PS/2
// devices) and waits on <dir>/ctl. A line "run <stdin> <stdout> <ps2 dir> <frames dir> <frame every> <pid file> <flags> <next cycle> <next dir>" makes the master fork a run that goes on from
// the checkpoint with that stdin/stdout, input directory and frame directory; "quit" ends the master.
static std::string g_ckpt_framedir;
static long long g_ckpt_frame_every = 0, g_ckpt_flags = 0, g_ckpt_next = 0;
void host_checkpoint(long long cycles) {
  const char* d = getenv("BARG_CKPT_DIR");
  if (!d || !*d) return;
  std::string dir = d, ctl = dir + "/ctl";
  mkdir(dir.c_str(), 0755);
  unlink(ctl.c_str());
  if (mkfifo(ctl.c_str(), 0600) != 0) return;
  fflush(stdout); fflush(stderr);
  pid_t m = fork();
  if (m != 0) {                             // the original run goes on; it can park a later checkpoint too
    const char* nc = getenv("BARG_CKPT_CHAIN"); const char* nd = getenv("BARG_CKPT_CHAIN_DIR");
    if (nc && nd && *nd) { g_ckpt_next = atoll(nc); setenv("BARG_CKPT_DIR", nd, 1); }
    return;
  }
  setsid();
  signal(SIGCHLD, SIG_IGN);
  signal(SIGPIPE, SIG_IGN);
  int dn = open("/dev/null", O_RDWR);
  dup2(dn, 0); dup2(dn, 1); dup2(dn, 2);
  { FILE* f = fopen((dir + "/info.tmp").c_str(), "w"); if (f) { fprintf(f, "%d %lld\n", (int)getpid(), cycles); fclose(f); rename((dir + "/info.tmp").c_str(), (dir + "/info").c_str()); } }
  FILE* in = fopen(ctl.c_str(), "r+");     // read-write: never sees end of file while the master lives
  if (!in) _exit(1);
  char line[8192];
  while (fgets(line, sizeof line, in)) {
    char cmd[16], si[1024], so[1024], pd[1024], fd2[1024], pf[1024];
    long long fe = 0, fl = 0, nc = 0;
    char nd[1024];
    if (strncmp(line, "quit", 4) == 0) { unlink((dir + "/info").c_str()); _exit(0); }
    if (sscanf(line, "%15s %1023s %1023s %1023s %1023s %lld %1023s %lld %lld %1023s", cmd, si, so, pd, fd2, &fe, pf, &fl, &nc, nd) != 10 || strcmp(cmd, "run") != 0) continue;
    pid_t c = fork();
    if (c == 0) {
      setsid();
      signal(SIGCHLD, SIG_DFL);
      signal(SIGPIPE, SIG_DFL);
      int i = open(si, O_RDONLY | O_NONBLOCK), o = open(so, O_WRONLY);
      if (i >= 0) dup2(i, 0);
      if (o >= 0) { dup2(o, 1); dup2(o, 2); }
      setenv("BARG_PS2_DIR", pd, 1);
      g_ps2_pos[0] = g_ps2_pos[1] = 0;
      g_ckpt_framedir = fd2; g_ckpt_frame_every = fe; g_ckpt_flags = fl;
      g_ckpt_next = (strcmp(nd, "-") != 0) ? nc : 0;
      if (g_ckpt_next > 0) setenv("BARG_CKPT_DIR", nd, 1);
      { FILE* f = fopen(pf, "w"); if (f) { fprintf(f, "%d\n", (int)getpid()); fclose(f); } }
      fclose(in);
      do_init();
      return;                                // the run goes on from the checkpoint
    }
  }
  _exit(0);
}
int host_ckpt_framedir_len() { return (int)g_ckpt_framedir.size(); }
int host_ckpt_framedir_ch(int i) { return i >= 0 && i < (int)g_ckpt_framedir.size() ? (unsigned char)g_ckpt_framedir[i] : 0; }
long long host_ckpt_next() { return g_ckpt_next; }
long long host_ckpt_flags() { return g_ckpt_flags; }
long long host_ckpt_frame_every() { return g_ckpt_frame_every; }

void host_finish(long long cycles) {
  fflush(stdout);
  restore();
  fprintf(stderr, "\n[simulation ended after %lld cycles]\n", cycles);
}

}  // extern "C"
