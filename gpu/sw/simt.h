/* Intrinsics for the BARG SIMT GPU (demos/simt-gpu/ISA.md), for riscv64-elf-gcc -march=rv32im -mabi=ilp32.
 *
 * Every thread runs the kernel; divergence has to be written with SIMT_IF / SIMT_ELSE / SIMT_ENDIF, and loops whose trip count
 * differs between threads with SIMT_WHILE. A plain `if` on a value that differs between the threads of a warp is a
 * divergent branch, which the hardware does not support (the model stops on it).
 *
 * THE ONE RULE OF DIVERGENT CODE WITH A STOCK COMPILER: a variable that is written inside a SIMT_IF / SIMT_ELSE / SIMT_WHILE
 * body and read after it must be `volatile`. GCC does not know that split and join change which threads are active, and it
 * moves register arithmetic across them (it sank `v = 3 * v + 1` below the join in collatz.c, so the even threads computed it
 * too). The asm statements below order memory; a volatile variable lives in memory, so its stores cannot leave the region.
 * Vortex avoids the rule with an LLVM pass that inserts split/join itself; that is the long-term fix here too.
 */
#ifndef SIMT_H
#define SIMT_H

#define SIMT_CSR(name, addr) \
    static inline unsigned simt_##name(void) { unsigned v; __asm__ volatile("csrr %0, " #addr : "=r"(v)); return v; }
SIMT_CSR(tid, 0xCC0)
SIMT_CSR(wid, 0xCC1)
SIMT_CSR(cid, 0xCC2)
SIMT_CSR(tmask, 0xCC3)
SIMT_CSR(gtid, 0xCC4)
SIMT_CSR(karg, 0xCC5)
SIMT_CSR(nt, 0xFC0)
SIMT_CSR(nw, 0xFC1)
SIMT_CSR(nc, 0xFC2)
SIMT_CSR(cycle, 0xC00)

/* Threads in the whole launch (one core in v0). */
static inline unsigned simt_nthreads(void) { return simt_nt() * simt_nw() * simt_nc(); }

static inline void simt_tmc(unsigned mask) { __asm__ volatile(".insn r 0x0B, 0, 0, x0, %0, x0" :: "r"(mask) : "memory"); }
static inline void simt_wspawn(unsigned n, void (*pc)(void)) {
    __asm__ volatile(".insn r 0x0B, 1, 0, x0, %0, %1" :: "r"(n), "r"(pc) : "memory");
}
static inline void simt_split(int pred) { __asm__ volatile(".insn r 0x0B, 2, 0, x0, %0, x0" :: "r"(pred) : "memory"); }
static inline void simt_join(void) { __asm__ volatile(".insn r 0x0B, 3, 0, x0, x0, x0" ::: "memory"); }
/* Wait until `count` warps have reached barrier `id` (0..3): __syncthreads() for the warps of the core. */
static inline void simt_barrier(unsigned id, unsigned count) {
    __asm__ volatile(".insn r 0x0B, 4, 0, x0, %0, %1" :: "r"(id), "r"(count) : "memory");
}
static inline int simt_any(int p) { int v; __asm__ volatile(".insn r 0x0B, 5, 0, %0, %1, x0" : "=r"(v) : "r"(p)); return v; }
static inline int simt_all(int p) { int v; __asm__ volatile(".insn r 0x0B, 5, 1, %0, %1, x0" : "=r"(v) : "r"(p)); return v; }
static inline unsigned simt_ballot(int p) {
    unsigned v; __asm__ volatile(".insn r 0x0B, 5, 2, %0, %1, x0" : "=r"(v) : "r"(p)); return v;
}
static inline int simt_shfl_idx(int x, int lane) { int v; __asm__ volatile(".insn r 0x0B, 6, 0, %0, %1, %2" : "=r"(v) : "r"(x), "r"(lane)); return v; }
static inline int simt_shfl_xor(int x, int m) { int v; __asm__ volatile(".insn r 0x0B, 6, 1, %0, %1, %2" : "=r"(v) : "r"(x), "r"(m)); return v; }
static inline int simt_shfl_up(int x, int d) { int v; __asm__ volatile(".insn r 0x0B, 6, 2, %0, %1, %2" : "=r"(v) : "r"(x), "r"(d)); return v; }
static inline int simt_shfl_down(int x, int d) { int v; __asm__ volatile(".insn r 0x0B, 6, 3, %0, %1, %2" : "=r"(v) : "r"(x), "r"(d)); return v; }

/* Divergence. Each path runs with only its threads active; SIMT_ENDIF brings the warp back together. */
#define SIMT_IF(cond)  do { int simt_p_ = (cond) != 0; simt_split(simt_p_); if (simt_p_) {
#define SIMT_ELSE      } else {
#define SIMT_ENDIF     } simt_join(); } while (0)
/* A loop whose trip count differs between threads: it runs while any thread's cond holds, the others idle.
 * The body is variadic so that commas in it (declarations, calls) do not split the macro's arguments. */
#define SIMT_WHILE(cond, ...) \
    do { for (;;) { int simt_w_ = (cond) != 0; if (!simt_any(simt_w_)) break; SIMT_IF(simt_w_) { __VA_ARGS__; } SIMT_ENDIF; } } while (0)

/* The tensor unit (all 4 threads of the warp must be active). Each warp has a 4 x 4 accumulator of 32-bit values inside the
 * unit, as Blackwell's tensor memory: thread i owns row i of it.
 *   simt_mma_zero()            acc = 0
 *   simt_mma_i8(a_row, b_col)  acc += A x B; thread i passes row i of A, thread j column j of B (four int8, element k in bits 8k+7..8k)
 *   simt_mma_ld(col)           returns acc[thread][col]
 *   simt_mma_st(v, col)        acc[thread][col] = v (an initial C or a bias) */
static inline void simt_mma_zero(void) { __asm__ volatile(".insn r 0x2B, 3, 0, x0, x0, x0" ::: "memory"); }
static inline void simt_mma_i8(unsigned a_row, unsigned b_col) {
    __asm__ volatile(".insn r 0x2B, 0, 0, x0, %0, %1" :: "r"(a_row), "r"(b_col) : "memory");
}
static inline int simt_mma_ld(unsigned col) { int v; __asm__ volatile(".insn r 0x2B, 1, 0, %0, %1, x0" : "=r"(v) : "r"(col) : "memory"); return v; }
static inline void simt_mma_st(int v, unsigned col) { __asm__ volatile(".insn r 0x2B, 2, 0, x0, %0, %1" :: "r"(v), "r"(col) : "memory"); }

/* Graphics (demos/simt-gpu/gfx, docs/gfx-architecture.md).
 *   simt_gfx_cfg(reg, v)  graphics register reg = v (the lowest active lane's operands)
 *   simt_pix(pos, argb)   write ARGB8888 colour argb at pixel pos = (y << 16) | x; dropped when off the screen or outside the box */
static inline void simt_gfx_cfg(unsigned reg, unsigned v) { __asm__ volatile(".insn r 0x5B, 0, 0, x0, %0, %1" :: "r"(reg), "r"(v) : "memory"); }
static inline void simt_pix(unsigned pos, unsigned argb) { __asm__ volatile(".insn r 0x5B, 5, 0, x0, %0, %1" :: "r"(pos), "r"(argb) : "memory"); }
/*   simt_rast()           this lane's pixel of the warp's next group: (y << 16) | x, y = 0xFFFF when it is not covered;
 *                         0xFFFFFFFF in every lane when the warp's scan is done (gfx.cfg 8 restarts it)
 *   simt_rast_edge(p, i)  edge function i (0..2) of the triangle at pixel p = (y << 16) | x, signed */
static inline unsigned simt_rast(void) { unsigned v; __asm__ volatile(".insn r 0x5B, 1, 0, %0, x0, x0" : "=r"(v) :: "memory"); return v; }
/*   simt_tex(u, v)        the texture at (u, v), unsigned 8.8 texels: ARGB8888 (gfx.cfg 32: bilinear, clamp u, clamp v) */
static inline unsigned simt_tex(unsigned u, unsigned v) { unsigned r; __asm__ volatile(".insn r 0x5B, 4, 0, %0, %1, %2" : "=r"(r) : "r"(u), "r"(v)); return r; }
/*   simt_ztest(p, z)      ~0 when depth z (16 bits) is nearer than the depth memory's at pixel p (which then becomes z), else 0 */
static inline unsigned simt_ztest(unsigned p, unsigned z) { unsigned r; __asm__ volatile(".insn r 0x5B, 6, 0, %0, %1, %2" : "=r"(r) : "r"(p), "r"(z) : "memory"); return r; }
static inline int simt_rast_edge(unsigned p, unsigned i) { int v; __asm__ volatile(".insn r 0x5B, 3, 0, %0, %1, %2" : "=r"(v) : "r"(p), "r"(i)); return v; }

/* Shared memory: `SIMT_SHARED int tile[64];` puts the array in the 4 KB scratchpad at 0x2000_0000. */
#define SIMT_SHARED __attribute__((section(".shared")))

/* The kernel every thread runs (defined by the kernel file). */
void kernel(void);

#endif
