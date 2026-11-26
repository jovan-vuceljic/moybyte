// moy_codec_aw88298: moy_codec_aw88298.h has the contract. The sequence is
// M5Unified's (_speaker_enabled_cb_cores3, MIT, m5stack/M5Unified): boost off,
// I2S enabled with the amplifier powered, the rate's code, full volume. Its
// registers are 16 bits, written high byte first.

#include "moy_codec_aw88298.h"
#include "moy_aud.h"            // MOY_ON_BOARD

#if MOY_ON_BOARD
#include "py/mpconfig.h"        // the board's MOY_AUDIO_CODEC_AW88298
#endif

#if MOY_ON_BOARD && MOY_AUDIO_CODEC_AW88298

#include <stddef.h>
#include <stdint.h>

#include "moy_bus.h"

static int wr(uint8_t dev, uint8_t reg, uint16_t v) {
    uint8_t b[3] = {reg, (uint8_t)(v >> 8), (uint8_t)v};
    return moy_bus_write(dev, b, 3);
}

// Register 0x06's rate field: the first of these at or above the rate in
// units of 2205 Hz, rounded (8 kHz .. 96 kHz).
static const uint8_t RATES[] = {4, 5, 6, 8, 10, 11, 15, 20, 22, 44};

const char *moy_aw88298_init(int rate) {
    uint8_t dev;
    if (moy_bus_add(MOY_AW88298_ADDR, 50, &dev) != MOY_BUS_OK) {
        return "the I2C bus would not take the AW88298";
    }
    unsigned code = 0, r = (unsigned)(rate + 1102) / 2205;
    while (code < sizeof(RATES) - 1 && r > RATES[code]) {
        code++;
    }
    if (wr(dev, 0x61, 0x0673) != MOY_BUS_OK) {          // boost mode off
        return "the AW88298 does not answer on the bus";
    }
    if (wr(dev, 0x04, 0x4040) != MOY_BUS_OK             // I2SEN, amplifier and chip up
        || wr(dev, 0x05, 0x0008) != MOY_BUS_OK          // unmuted, no AGC
        || wr(dev, 0x06, (uint16_t)(0x14C0 | code)) != MOY_BUS_OK   // 16-bit Philips, BCK 32 fs
        || wr(dev, 0x0C, 0x0064) != MOY_BUS_OK) {       // full volume
        return "the AW88298 refused its setup";
    }
    return NULL;
}

#endif
