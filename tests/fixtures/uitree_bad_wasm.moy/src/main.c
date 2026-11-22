// A compiled app whose page names a state it never declared
// (tests/test_uitree_wasm.py): the engine refuses it in _init, which
// tools/wasm_cart.py's check reports at build time.
#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

static void page(void) {
    ut_page("bad", "Bad") ut_label("{nothing}");
}

EXPORT(_init) void _init(void) { ut_open(page); }

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
