// moy_pad3: the Faces Gamepad3's driver; moy_drivers.h has the contract.

#include "moy_drivers.h"

#include "moy_input.h"

// The byte's bits in order, each the table's button.
static const char *const PAD3_BUTTONS[8] = {
    "up", "down", "left", "right", "a", "b", "select", "start",
};

static uint32_t bit_of(const char *name) {
    for (int i = 0; i < MOY_INPUT_BUTTONS; i++) {
        const char *a = MOY_INPUT_NAMES[i], *b = name;
        while (*a && *a == *b) {
            a++;
            b++;
        }
        if (*a == 0 && *b == 0) {
            return 1u << i;
        }
    }
    return 0;
}

uint32_t moy_pad3_buttons(uint8_t raw) {
    uint32_t held = 0;
    for (int i = 0; i < 8; i++) {
        if (!(raw & (1u << i))) {
            held |= bit_of(PAD3_BUTTONS[i]);
        }
    }
    return held;
}

#define PAD3_LEFT 0x04u
#define PAD3_RIGHT 0x08u
#define PAD3_A 0x10u
#define PAD3_B 0x20u
#define PAD3_SELECT 0x40u

uint32_t moy_pad3_held(uint8_t raw, bool game) {
    uint8_t down = (uint8_t)~raw;
    if (!(down & PAD3_SELECT)) {
        return moy_pad3_buttons(raw);
    }
    uint32_t chord = 0;
    if (down & PAD3_A) {
        chord |= bit_of("x");
    }
    if (down & PAD3_B) {
        chord |= bit_of("y");
    }
    down &= (uint8_t)~(PAD3_A | PAD3_B);
    if (!game) {
        down &= (uint8_t)~(PAD3_LEFT | PAD3_RIGHT);
    }
    return moy_pad3_buttons((uint8_t)~down) | chord;
}

int moy_pad3_typed(uint8_t was, uint8_t raw, bool quiet) {
    uint8_t down = (uint8_t)~raw, edge = (uint8_t)(was & ~raw);
    if (quiet || !(down & PAD3_SELECT)) {
        return 0;
    }
    return edge & PAD3_LEFT ? 'q' : edge & PAD3_RIGHT ? 'e' : 0;
}

void moy_pad3_init(moy_pad3_t *p, void *table, uint32_t src) {
    p->available = false;
    p->addr = MOY_PAD3_ADDR;
    p->gate = false;
    p->int_low = false;
    p->last_read_ms = 0;
    p->raw = 0xFF;
    p->reprobe = 0;
    p->table = table;
    p->src = src;
    p->reads = 0;
    p->errors = 0;
}

void moy_pad3_probe(moy_pad3_t *p, const moy_i2c_t *bus) {
    uint8_t reg = MOY_PAD3_MODEL_REG, model = 0;
    p->available = bus->write_read(bus->ctx, p->addr, &reg, 1, &model, 1) == 0
                   && model == MOY_PAD3_MODEL;
    p->last_read_ms = bus->ms(bus->ctx);
}

void moy_pad3_pass(moy_pad3_t *p, const moy_i2c_t *bus) {
    if (!p->available) {
        if (++p->reprobe >= MOY_TOUCH_REPROBE) {     // a face plugged in later
            p->reprobe = 0;
            moy_pad3_probe(p, bus);
        }
        return;
    }
    if (p->gate && !p->int_low) {
        return;                         // nothing new: the face would answer stale bytes
    }
    p->last_read_ms = bus->ms(bus->ctx);
    uint8_t reg = MOY_PAD3_KEY_REG, raw;
    p->reads++;
    if (bus->write_read(bus->ctx, p->addr, &reg, 1, &raw, 1) != 0) {
        p->errors++;
        return;
    }
    if (raw == 0x00) {
        return;                         // the firmware's stale buffer, not eight buttons
    }
    if (raw != p->raw) {
        uint8_t was = p->raw;
        p->raw = raw;
        moy_input_t *t = (moy_input_t *)p->table;
        moy_input_set_mask(t, p->src, moy_pad3_held(raw, moy_input_cart_keys(t)));
        int key = moy_pad3_typed(was, raw, moy_input_cart_keys(t) || moy_input_text_mode(t));
        if (key) {
            moy_input_key(t, p->src, key);
        }
    }
}

size_t moy_pad3_sizeof(void) {
    return sizeof(moy_pad3_t);
}
