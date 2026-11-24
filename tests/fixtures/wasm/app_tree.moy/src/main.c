// App Tree Wasm: a compiled app's page of the toolkit's widgets on the UI
// tree (sdk/include/moybyte/uitree.h), which tests/on_glass.py runs on a
// board and holds to the host's run of the same page by its pixels.
// It needs no permission: the uitree rows are every compiled app's, served in
// C, so the run makes no upcall. Into pmem (moy-spec's "moy" pmem row):
// 0 frames, 8 the last row answer that failed, negated (0: none).
#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))
#define MOY_IMPORT(name) __attribute__((import_module("moy"), import_name(#name)))

int32_t moy_pmem(int32_t slot, int32_t v, int32_t write) MOY_IMPORT(pmem);

enum { P_FRAMES = 0, P_FAIL = 8 };
static int32_t s_count, s_frames;

static void failed(int32_t r) {
    if (r < 0) {
        moy_pmem(P_FAIL, -r, 1);
    }
}

static void add(int32_t row) { uitree_set_int(s_count, uitree_get_int(s_count) + 1); }

static void page(void) {
    ut_page("widgets", "Widgets") {
        ut_group("Sound") {
            ut_toggle("muted", "Mute");
            ut_progress("{level}", "Level", 10);
            ut_info("Presses", "{count}");
        }
        ut_group("Name") {
            ut_field("name", "Name");
            ut_button("add", NULL);
            ut_link("add", NULL);
        }
    }
}

EXPORT(_init) void _init(void) {
    s_count = ut_int("count", 0);
    failed(ut_int("level", 6));
    failed(ut_bool("muted", 1));
    failed(ut_text("name", "Moy"));
    ut_action("add", "Add one", add);
    ut_open(page);
}

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) {
    failed(ut_frame());
    s_frames++;
    moy_pmem(P_FRAMES, s_frames, 1);
}
