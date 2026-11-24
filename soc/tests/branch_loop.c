/* Branch-heavy loops with no memory traffic in the loop bodies: nested counted loops (the branch back is taken most of the time), a
 * data-dependent if/else on a counter (taken every third time), and a call in the loop. A static not-taken pipeline pays two bubbles for every
 * taken branch; gshare should learn all three patterns. TOHOST 1 = the sums are right; the cycle count is what is compared. */
#include <stdint.h>
#define R(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define TOHOST 0x80FFF000u
static uint32_t __attribute__((noinline)) f(uint32_t x) { return x * 3 + 1; }
int main(void) {
    uint32_t s = 0, t = 0;
    for (uint32_t i = 0; i < 40; i++)
        for (uint32_t j = 0; j < 40; j++) {
            if (j % 3 == 0) s += j; else s ^= i;
            t += f(j) & 7;
        }
    R(TOHOST) = (s != 0 || t != 0) ? 1 : 2;
    for (;;) ;
}
