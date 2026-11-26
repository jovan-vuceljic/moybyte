// moy_codec_aw88298: the AW88298 the CoreS3 carries, a class-D amplifier with
// an I2S input and an I2C control port at 0x36 on the kernel's bus
// (native/moy_kernel/moy_bus.h). It takes 16-bit Philips I2S at 32 BCK a
// frame, clocked by BCK (no MCLK of its own). A board takes it with
// MOY_AUDIO_CODEC_AW88298 in mpconfigboard.h (native/moy_audio/moy_aud_out.c);
// whatever powers the amplifier's rail is the board's.

#ifndef MOY_CODEC_AW88298_H
#define MOY_CODEC_AW88298_H

#define MOY_AW88298_ADDR 0x36

// The register sequence for `rate`: NULL when the amplifier answered and took
// it, else what went wrong.
const char *moy_aw88298_init(int rate);

#endif // MOY_CODEC_AW88298_H
