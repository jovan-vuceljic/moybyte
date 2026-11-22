// Conformance fixture `pictures` (level 2), the compiled half: a seg of
// look="pictures" over an enum, each value's word an image's text (no picture
// put: the engine's plates alone), and a label of its value
// (sdk/include/moybyte/uitree.h). Its Python half is ../app.py, its Lua half
// ../pictures.moy.
#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

static void page(void) {
    ut_page("pictures", "Pictures") {
        ut_seg_look("face", "Face", "FACES", UT_LOOK_PICTURES);
        ut_label("Face {face}");
    }
}

EXPORT(_init) void _init(void) {
    ut_enum("face", "x\0y\0z", "x");
    uitree_labels("FACES", 5, "x\0y\0z", 5, "own:face:x\0own:face:y\0own:face:z", 32);
    ut_open(page);
}

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
