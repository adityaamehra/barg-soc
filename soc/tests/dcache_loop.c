/* 20 passes over a 512-byte array (2000 word loads): with a data cache the passes after the first hit, so the run takes far fewer cycles than
 * 2000 x the memory latency. TOHOST 1 = the checksum is right. */
#include <stdint.h>
#define R(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define A 0x80F10000u
#define TOHOST 0x80FFF000u
int main(void) {
    for (uint32_t i = 0; i < 128; i++) R(A + 4 * i) = i * 3 + 1;
    uint32_t s = 0;
    for (int pass = 0; pass < 20; pass++) for (uint32_t i = 0; i < 128; i++) s += R(A + 4 * i);
    R(TOHOST) = s == 20u * (3u * (127 * 128 / 2) + 128) ? 1 : s * 2 + 3;
    for (;;) ;
}
