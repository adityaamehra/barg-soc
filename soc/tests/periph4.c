/* Bare-metal test of the peripheral window: GPIO (loopback of pins 7:0, pins 15:12 held high), SPI master (MISO wired to MOSI), I2C master (slave at 0x50).
 * TOHOST 1 = pass, else 2*check+1 for the first failing check. */
#include <stdint.h>
#define R(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define GPIO 0x10010000u
#define SPI  0x10010100u
#define I2C  0x10010200u
#define TOHOST 0x80FFF000u
static int fails; static uint32_t first_fail;
static void check(uint32_t n, int ok) { if (!ok && !fails) first_fail = n; if (!ok) fails++; }
static void delay(int n) { for (volatile int i = 0; i < n; i++) ; }
static uint32_t spi_xfer(uint32_t cs, uint32_t w) {
    R(SPI + 8) = cs; R(SPI + 4) = 2;                         /* chip select; clear done */
    R(SPI + 0) = w;
    while (!(R(SPI + 4) & 2)) ;
    return R(SPI + 0);
}
static uint32_t i2c_cmd(uint32_t cmd) {                    /* returns the status after the command finished */
    R(I2C + 4) = 2;
    R(I2C + 0) = cmd;
    uint32_t s; do s = R(I2C + 4); while (!(s & 2));
    return s;
}
int main(void) {
    /* GPIO */
    R(GPIO + 4) = 0xFF;                                      /* direction: pins 7:0 are outputs */
    R(GPIO + 0) = 0xA5; delay(20);
    check(1, R(GPIO + 4) == 0xFF);
    check(2, R(GPIO + 0) == (0xF000u | 0xA5));               /* output loopback and the held-high pins */
    R(GPIO + 0) = 0x00; delay(20); R(GPIO + 0xC) = 0xFFFF;  /* drop all, clear pending */
    R(GPIO + 8) = 0x0008;                                    /* enable pin 3's interrupt */
    check(3, R(GPIO + 0xC) == 0);
    R(GPIO + 0) = 0x08; delay(20);
    check(4, R(GPIO + 0xC) == 0x0008);                      /* the rising edge of pin 3 is pending */
    R(GPIO + 0xC) = 0x0008; delay(20);
    check(5, R(GPIO + 0xC) == 0);                           /* write one to clear */
    /* SPI */
    check(6, spi_xfer(1, 0x5A) == 0x5A);
    check(7, spi_xfer(2, 0xC3) == 0xC3);
    check(8, spi_xfer(0, 0x01) == 0x01);
    check(9, (R(SPI + 4) & 1) == 0);                         /* not busy */
    /* I2C: write 0x11 to the device at 0x50, read two bytes back, address 0x51 is not acknowledged */
    uint32_t s;
    s = i2c_cmd(0xA0 | (1u << 8));         check(10, !(s & 4));                 /* START, address 0x50 write: ACK */
    s = i2c_cmd(0x11 | (1u << 9));         check(11, !(s & 4));                 /* data, STOP */
    s = i2c_cmd(0xA1 | (1u << 8));         check(12, !(s & 4));                 /* START, address 0x50 read: ACK */
    s = i2c_cmd(1u << 11);                 check(13, R(I2C + 0) == 0x3C);       /* read a byte, ACK */
    s = i2c_cmd((1u << 11) | (1u << 9) | (1u << 10)); check(14, R(I2C + 0) == 0x3D);   /* read a byte, NACK, STOP */
    s = i2c_cmd(0xA2 | (1u << 8) | (1u << 9)); check(15, (s & 4) != 0);         /* address 0x51: NACK */
    R(TOHOST) = fails ? 2 * first_fail + 1 : 1;
    for (;;) ;
}
