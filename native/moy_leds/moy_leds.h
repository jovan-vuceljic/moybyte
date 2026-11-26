// moy_leds: a board's RGB LEDs as one device (the `leds` device API,
// native/moy_kernel/moy_dev.h): one process holds them at a time, sets each
// LED's colour or the whole bar's and their brightness, and when it lets go
// -- its close, its end (exit, crash, kill: moy_leds_sweep), a VM's stop --
// they go dark.
//
// The LEDs are the board's: it answers how many (moy_board_leds) and shows a
// frame (moy_board_leds_show), both weak, so a board with none has a count
// of 0 and every open is ABSENT. The host has none: moy_leds_sim(n) makes a
// bar of n and moy_leds_shown reads back the last frame shown.
//
// A colour is 0xRRGGBB; the frame handed to the board is GRB, three bytes an
// LED, each channel scaled by the brightness (0..255, 255 at an open). Every
// call takes the lease table's lock (moy_lease.h), which the handle table
// holds around a kind's call too. The answers are 0 or a negative errno:
// -ENODEV without LEDs, -EBUSY while another process holds them, -EPERM for
// a call by one that does not, -EINVAL for an LED past the bar.

#ifndef MOY_LEDS_H
#define MOY_LEDS_H

#include <stddef.h>
#include <stdint.h>

#define MOY_LEDS_MAX 64             // the most LEDs a board's bar can name

uint32_t moy_leds_count(void);
int moy_leds_open(uint32_t owner);
int moy_leds_close(uint32_t owner);
uint32_t moy_leds_sweep(uint32_t owner);   // its end: 1 when it held them
uint32_t moy_leds_owner(void);
int moy_leds_set(uint32_t owner, uint32_t i, uint32_t rgb);
int moy_leds_fill(uint32_t owner, uint32_t rgb);
int moy_leds_bright(uint32_t owner, uint32_t level);
// A frame of 0xRRGGBB colours as bytes R G B, an LED each from the first;
// the LEDs past it go dark.
int moy_leds_write(uint32_t owner, const uint8_t *rgb, uint32_t n);
// The last frame shown, GRB, into `out`: the bytes written.
int moy_leds_shown(uint8_t *out, uint32_t n);
void moy_leds_sim(uint32_t n);
void moy_leds_reset(void);

// The board's half (weak).
uint32_t moy_board_leds(void);
void moy_board_leds_show(const uint8_t *grb, uint32_t n);

#endif // MOY_LEDS_H
