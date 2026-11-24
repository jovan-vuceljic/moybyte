// The module `moy_improv`: Improv Wi-Fi's frames on the USB-Serial/JTAG
// console (moy_improv.h), on a board whose mpconfigboard.h defines MOY_IMPROV
// (the Zeros). The console's receive path calls moy_improv_usj on every read
// (tools/patch_usj_improv.py), in its ISR or under its lock; the frames it
// finds wait in a ring of FRAMES for the store host's loop, which answers
// them (device/zero_improv.py):
//
//   take() -> (type, data) of the next frame, or None; type is -1 for a
//             frame whose checksum did not add up. It first reads what the
//             console's FIFO holds, so a frame sent while the board booted is
//             taken. While the store host serves nothing reads the REPL's
//             input, and a full ring of it would stop the console reading the
//             FIFO, frames and all: take() empties a FULL ring.
//   send(type, data)  one frame out on the console (moy_improv_frame).
//
// A frame that finds the ring full is dropped: the client asks again.

#include "py/runtime.h"

#if MOY_IMPROV

#include <string.h>

#include "py/mphal.h"
#include "py/ringbuf.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "usb_serial_jtag.h"

#include "moy_improv.h"

#define FRAMES 2

typedef struct {
    int16_t type;
    uint8_t n;
    uint8_t data[MOY_IMPROV_DATA_MAX];
} frame_t;

static moy_improv_rx_t s_rx;
static frame_t s_q[FRAMES];
static volatile uint8_t s_head, s_count;
static portMUX_TYPE s_mux = portMUX_INITIALIZER_UNLOCKED;

static uint32_t now_ms(void) {
    return (uint32_t)(esp_timer_get_time() / 1000);
}

static void lock(void) {
    if (xPortInIsrContext()) {
        portENTER_CRITICAL_ISR(&s_mux);
    } else {
        portENTER_CRITICAL(&s_mux);
    }
}

static void unlock(void) {
    if (xPortInIsrContext()) {
        portEXIT_CRITICAL_ISR(&s_mux);
    } else {
        portEXIT_CRITICAL(&s_mux);
    }
}

static void queue(void *ctx, int type, const uint8_t *data, size_t n) {
    (void)ctx;
    if (s_count >= FRAMES) {
        return;
    }
    frame_t *f = &s_q[(s_head + s_count) % FRAMES];
    f->type = (int16_t)type;
    f->n = (uint8_t)n;
    memcpy(f->data, data, n);
    s_count++;
}

// The console's read of `n` bytes in `buf` (room for `cap`): the bytes that
// are the REPL's, in place, and their count. n == 0 is a tick.
size_t moy_improv_usj(uint8_t *buf, size_t n, size_t cap) {
    uint8_t in[64 + MOY_IMPROV_HOLD];
    if (n > sizeof in || cap < n + MOY_IMPROV_HOLD) {
        return n;                               // never a read the patch did not size
    }
    memcpy(in, buf, n);
    lock();
    uint32_t now = now_ms();
    size_t o = moy_improv_tick(&s_rx, now, buf);
    o += moy_improv_feed(&s_rx, in, n, now, buf + o, queue, NULL);
    unlock();
    return o;
}

int moy_improv_held(void) {
    return moy_improv_busy(&s_rx);
}

static mp_obj_t mod_take(void) {
    if (ringbuf_free(&stdin_ringbuf) == 0) {
        stdin_ringbuf.iget = stdin_ringbuf.iput;
    }
    usb_serial_jtag_poll_rx();
    frame_t f;
    lock();
    int had = s_count > 0;
    if (had) {
        f = s_q[s_head];
        s_head = (uint8_t)((s_head + 1) % FRAMES);
        s_count--;
    }
    unlock();
    if (!had) {
        return mp_const_none;
    }
    mp_obj_t t[2] = { MP_OBJ_NEW_SMALL_INT(f.type), mp_obj_new_bytes(f.data, f.n) };
    return mp_obj_new_tuple(2, t);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_take_obj, mod_take);

static mp_obj_t mod_send(mp_obj_t type, mp_obj_t data) {
    mp_buffer_info_t b;
    mp_get_buffer_raise(data, &b, MP_BUFFER_READ);
    if (b.len > MOY_IMPROV_DATA_MAX) {
        mp_raise_ValueError(MP_ERROR_TEXT("frame too long"));
    }
    uint8_t out[MOY_IMPROV_FRAME_MAX];
    size_t n = moy_improv_frame(mp_obj_get_int(type), b.buf, b.len, out);
    usb_serial_jtag_tx_strn((const char *)out, n);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(mod_send_obj, mod_send);

static const mp_rom_map_elem_t moy_improv_globals[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_moy_improv) },
    { MP_ROM_QSTR(MP_QSTR_take), MP_ROM_PTR(&mod_take_obj) },
    { MP_ROM_QSTR(MP_QSTR_send), MP_ROM_PTR(&mod_send_obj) },
};
static MP_DEFINE_CONST_DICT(moy_improv_globals_dict, moy_improv_globals);

const mp_obj_module_t moy_improv_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&moy_improv_globals_dict,
};

MP_REGISTER_MODULE(MP_QSTR_moy_improv, moy_improv_module);

#endif
