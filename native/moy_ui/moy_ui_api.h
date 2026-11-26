// The public UI API's engine (docs/history/ui_api_2026-10.md): the verbs every app
// and cart draws its interface with -- page, label, button, toggle, slider,
// list, group, info, link, cycle, seg, swatches, hints, icon, progress, table,
// scroll, field, dialog, popover, menu, tabs, grid, card, part, focus, keys_taken, at -- and
// the focus and navigation they share.
//
// Immediate mode over a CONTEXT the caller owns (moy_ui_ctx_t, plain bytes:
// the Python face's bytearray per app, the run's one static): the focused id,
// the stops the previous frame drew, each id's kept state (a page's scroll, a
// list's row) and the layout cursor. A context is of an INSTANCE
// (moy_ui_inst_t, below), what its frames share with its sibling contexts'.
// A frame begins with moy_ui_api_begin, which resolves the frame's input
// once over the previous frame's stops -- focus moves, activation, the
// pointer's press and drag, the page scroll that keeps focus in view -- and
// every verb after it draws through a sink (moy_ui.h) with the theme's
// marks: a stop's `focus=` and `on`.
//
// An id is its label's FNV-1a hash, or the override's `id`; a page's is its
// title's under a page salt. A verb's answer is its value: true the frame a
// button is activated, a toggle's and a slider's new value, a list's new row.

#ifndef MOY_UI_API_H
#define MOY_UI_API_H

#include <stddef.h>
#include <stdint.h>

#include "moy_ui.h"
#include "moy_ui_text.h"

#define MOY_UI_API_STOPS 40         // the stops one frame records
#define MOY_UI_API_KEEP 16          // the ids whose state is kept
#define MOY_UI_API_CAPS 16          // the group captions one frame records
#define MOY_UI_API_NAME 32          // the focused id's text, NUL-terminated
#define MOY_UI_API_TIP 48           // a tooltip's text, NUL-terminated
#define MOY_UI_API_FLOOR 24         // the rects a shift frame's floor holds
#define MOY_UI_API_DIVS 8           // the dividers one frame's splits record (moy_ui_api_split_at)
#define MOY_UI_API_PANES 16         // the panes one pass's splits record (moy_ui_api_split_frame)
#define MOY_UI_API_TROWS 48         // the rows of a carried table a frame keeps the record of
#define MOY_UI_API_PASTE 240        // the bytes the console's paste brings a field at most
#define MOY_UI_API_UNDO 256         // the bytes of a field's text a cancel gives back at most
#define MOY_UI_API_EDITS 4          // the fields' edits an instance keeps the start of at once

// The input a frame resolves over, the run snapshot's shape: the buttons held
// and pressed this frame (bit i is MOY_INPUT_NAMES[i]: left, right, up, down,
// a, b, run), the pointer (x, y and its flags: LIVE 1, HELD 2, the press edge
// 4), the key typed this frame (9 is Tab) and the modifiers held with it
// (moy_input.h's MOY_INPUT_MOD_*: Shift+Tab steps back), and the wheel's
// notches this frame, across and down (positive right and down): a notch
// down glides the page under the pointer MOY_UI_WHEEL_ROWS rows. No page
// scrolls across, so Shift's wheel, which turns it across, scrolls none.
// Then the loop's tick in ms, the clock the scrolling nests' motion runs on
// (moy_ui.h's moy_ui_scroll_t): the host's injected dt, never a clock read;
// 0, no clock, lands every glide at once and flings nothing. Then the
// steps this frame beyond the press edges (a held key's repeats, the
// trackball's steps; moy_input_rep_word): four 8-bit counts, left, right <<
// 8, up << 16, down << 24, each a step as a press of its direction is; and a
// held key's typing repeats: the byte in the low 16 bits and the count above
// (MOY_UI_KEYREP). A repeat is a step, never a press: nothing activates,
// opens or commits on one.
enum {
    MOY_UI_IN_BTN = 0, MOY_UI_IN_BTNP, MOY_UI_IN_X, MOY_UI_IN_Y, MOY_UI_IN_PTR, MOY_UI_IN_KEY,
    MOY_UI_IN_MODS, MOY_UI_IN_WHEEL_X, MOY_UI_IN_WHEEL_Y, MOY_UI_IN_DT, MOY_UI_IN_REP,
    MOY_UI_IN_KEYREP,
    MOY_UI_IN_LEN
};

// An app's host (runtime/toolkit/ui_draw.py's AppHost, moy_ui_api_host_begin): what
// the frames it painted left of its page in the buffers a canvas presents
// in turn, a slot a paint (the ring, newest at ri, rn held): the frame, its
// key (what the pixels are a function of besides the page: the look's
// epoch and the focus marks), whether it left the page whole with nothing
// over it, and what the console drew over it after its pass (over, where
// over_on). Then the lag history (moy_ui_api_lag's), the frame begun last
// (began1, its number + 1; 0 none), what that frame was (shifting, dy: a
// rows frame, a shift by dy), the move its begin planned for the host's
// canvas (mv_dy), whether the next frame draws whole (again) and whether the
// frame begun last let its page stand (stand). All zero is a host that
// painted nothing.
#define MOY_UI_HOST_RING 3          // the paints a host remembers (RETAINED_FRAMES at most)
#define MOY_UI_HOST_HIST 4          // the frames its lag history keeps
#define MOY_UI_HOST_BANDS 3         // the bands a frame's floor is kept as
typedef struct {
    int32_t f[MOY_UI_HOST_RING];
    int32_t key[MOY_UI_HOST_RING];
    int32_t over[MOY_UI_HOST_RING][4];
    uint8_t whole[MOY_UI_HOST_RING], over_on[MOY_UI_HOST_RING];
    uint8_t ri, rn, shifting, again, stand;
    int32_t hist[MOY_UI_HOST_HIST * (2 + 2 * MOY_UI_HOST_BANDS)];
    int32_t began1;
    int16_t dy, mv_dy;
} moy_ui_host_t;
// One paint of a context (its kept ring, moy_ui_api_kept.c's): the painted frame (-1:
// none), whether it is the app's alone (`kept`: no key of its table was
// negative), and its kept table (has_tbl), as moy_ui_api_table recorded it:
// its id, key, columns' geometry, view, scroll, row height and count,
// current row (its part `at`) and focus mark, the record (each part's cell
// hashed, np parts a row, the current part's gen in it) of rows r0 .. r0 +
// k - 1 (k -1: none kept), and what was
// drawn over it after its pass (`over`, w 0 none); then the parts `held`
// named (id, key), nh of them.
#define MOY_UI_KEPT_RING 4          // RETAINED_FRAMES at most, and the paint begun
#define MOY_UI_KEPT_HELD 8          // the parts `held` names a paint
#define MOY_UI_KEPT_FLOOR 4         // the rects a kept table's floor is merged to
#define MOY_UI_KEPT_PARTS 48        // the parts that show a kept table records (more: drawn whole)
#define MOY_UI_KF_HELD 1            // kf.held: every buffer holds the kept table
#define MOY_UI_KF_OVER 2            // ...but for what was drawn over it
// The faces a table's parts keep drawn (moy_ui_api_slots): the key and
// slots they are kept under, the uses counted, the warm order's next step,
// the parts it named this round (wn) and the table's rows it runs over
// (r0 .. r1 showed, of rows, np parts each);
// each slot's part key and last use (0: empty). An instance's one record,
// taken at its first moy_ui_api_slots (moy_ui_api_kept.c's kept memory).
#define MOY_UI_FACE_SLOTS 128       // the slots it keeps at most
typedef struct {
    uint32_t tick;
    int32_t key;
    uint16_t cap, w, wn;
    int16_t r0, r1, rows;
    uint8_t np;
    uint32_t pk[MOY_UI_FACE_SLOTS], used[MOY_UI_FACE_SLOTS];
} moy_ui_faces_t;

typedef struct {
    int32_t f, key, off;
    uint32_t id, geo;
    moy_ui_box_t view, over;
    int16_t rh, n, cur, r0, k;
    int8_t at;
    uint8_t mark, kept, has_tbl, nh, np;
    uint32_t h[MOY_UI_KEPT_PARTS];
    uint32_t hid[MOY_UI_KEPT_HELD];
    int32_t hkey[MOY_UI_KEPT_HELD];
} moy_ui_kept_t;
#define MOY_UI_KEYREP(byte, n) ((int32_t)(byte) | ((int32_t)(n) << 16))
#define MOY_UI_MOD_SHIFT 2
#define MOY_UI_WHEEL_ROWS 3
// MIDDLE: the pointer's middle button is held (a mouse's), which drags the
// page under it by its travel.
enum { MOY_UI_P_LIVE = 1, MOY_UI_P_HELD = 2, MOY_UI_P_EDGE = 4, MOY_UI_P_MIDDLE = 8 };
enum {
    MOY_UI_B_LEFT = 1, MOY_UI_B_RIGHT = 2, MOY_UI_B_UP = 4, MOY_UI_B_DOWN = 8, MOY_UI_B_A = 16,
    MOY_UI_B_B = 32, MOY_UI_B_RUN = 64
};
#define MOY_UI_KEY_TAB 9
// moy_input's MOY_INPUT_KEY_PGUP and MOY_INPUT_KEY_PGDN (a text view's page).
#define MOY_UI_KEY_PGUP 0x114
#define MOY_UI_KEY_PGDN 0x115

// A part's state bits (§5).
enum { MOY_UI_ST_FOCUS = 1, MOY_UI_ST_ACTIVATED = 2, MOY_UI_ST_PRESSED = 4, MOY_UI_ST_HOVER = 8 };

// The override table (§3): its keys, their kinds and the block's bits are
// native/moy_ui/over.json's (moy_ui_over_keys.h, generated). A wasm app
// hands it over as a block, a pointer and its length: the nine words (a
// colour a role as MOY_UI_O_ROLE + its index in the token row,
// moy_ui_token_names, or 0xRRGGBB; the id's text's length; a flag 0 or 1;
// -1 absent), the id's text, then, where it goes on, the hint's length as a
// word and its text, a word of flags and each key's words it names in its
// bits' order (docs/history/ui_api_2026-10.md §3).
#include "moy_ui_over_keys.h"
#define MOY_UI_O_ROLE 0x1000000
#define MOY_UI_O_NONE (-1)

typedef struct {
    int32_t fill, ink, border;      // MOY_UI_O_NONE, RGB, or MOY_UI_O_ROLE + a token
    moy_ui_span_t id;               // p NULL: the label's
    int8_t current, disabled, nav, mark;    // -1 absent
    int8_t steps;                   // a slider: 1 a segment per step, no number; 2 the same
                                    // blocks across the whole row (a meter)
    moy_ui_span_t hint;             // a field's placeholder (p NULL: none)
    int8_t wash;                    // a popover: wash what it covers (-1 absent), or
                                    // 2 ("view") its anchor's view alone, less the
                                    // anchor and its ring
    int8_t lead;                    // a table: its first row is a verb (-1 absent)
    int8_t has_gen;                 // `gen` given: 1, else 0
    int32_t gen;                    // what the app draws in the stop is a function of it
    // A table: its column 0 is a part `part_w` wide (0: the room its text
    // columns leave), its rows `part_h` tall (0: the theme's), where has_part.
    int8_t has_part;
    int16_t part_w, part_h;
    int8_t bar;                     // a table: its current row wears the cursor bar (-1 absent)
    // A table of parts: its rows lie side by side (`axis` "x": 1, else 0),
    // row 0 centred in the view at scroll 0 and a still view resting on a
    // row's centre (`snap`, 0 or 1); the app's own scroll (has_offset); what
    // a part may draw past its cell on every side (`spill`, px).
    int8_t axis_x, snap, has_offset;
    int32_t offset;
    int16_t spill;
    // A placed table of parts keeps its parts across frames (has_keep):
    // `keep` what every part is a function of beside its row's cells (a
    // negative key keeps nothing of this frame's paint); `whole` (0 or 1)
    // this frame draws its view whole (the app drew its ground anew);
    // `over_*` a rect drawn over the table after its pass this frame (a
    // cursor; w 0 none).
    int8_t has_keep, whole;
    int32_t keep;
    int16_t over_x, over_y, over_w, over_h;
    // `shift` (0 or 1): the app's ground is the same along the axis, so a
    // frame whose buffer lacks the table at its scroll may move the view
    // out of the buffer the last frame painted (moy_ui_api_table_shift);
    // `fade` px of the view's end along the axis the app blends after its
    // parts (a move carries blended pixels: they draw again).
    int8_t shift;
    int16_t fade;
    // A table of parts whose rows hold parts across (has_across): a row's
    // cells are its parts' keys, the first `across_first` px into the view
    // across the rows' axis, each `across_pitch` px on from the last; `at`
    // the current row's part its gen and marks belong to.
    int8_t has_across;
    int16_t across_first, across_pitch, at;
    // An info or a link row: the signal glyph (moy_ui.h's moy_ui_signal)
    // before its value, its lit bars + 1 (0: no glyph).
    int8_t signal;
    // A list: each row's secondary text, NUL-separated, at its right in the
    // dim ink (p NULL: none); `check` (0 or 1) the check icon at the
    // current row's right, its column kept on every row.
    moy_ui_span_t values;
    int8_t check;
    // A list's two-line rows (moy_ui.h's moy_ui_row2), each a text a row,
    // NUL-separated (p NULL: none): `subs` (its second line; given, the rows
    // are two-line), `icons` (its lead: an icon's name, or "@" and a
    // person's name for their initials), `counts` (its badge; "" or "0"
    // none), `tags` (a pill after its title) and `marks` (an icon there).
    moy_ui_span_t subs, icons, counts, tags, marks;
    // A group with no caption (ui.group("", {card = true})): 1 opens its card.
    int8_t card;
    // An info's or a link's tag: a pill at its value's right (p NULL: none).
    moy_ui_span_t tag;
    // A dialog's button focus opens on, by its label (p NULL: its body's
    // first stop, else its first button).
    moy_ui_span_t focus;
    // The block's second word of flags (MOY_UI_O_MORE; 0 none), which the
    // keys past the first word's read.
    int32_t flags2;
    // A bar item's icon alone at 16 units at the scale, centred in its box (its cell and its
    // tap the box's), as a labelled one's (the UI tree's on a page that is a bar, Moy's tile
    // apart); else the largest its box's height holds.
    int8_t small;
} moy_ui_over_t;

// Every key absent.
void moy_ui_over_none(moy_ui_over_t *o);
// sizeof(moy_ui_over_t): what a binding's mirror of it is held to.
size_t moy_ui_over_size(void);
// The block of `n` bytes at `w` (NULL or 0: every key absent) into *o, its id
// pointing into the block. MOY_UI_BAD where it is short or its id overruns.
int moy_ui_over_block(moy_ui_over_t *o, const uint8_t *w, size_t n);
// Every key, in the block's order: what each tier's reader walks.
extern const moy_ui_over_key_t moy_ui_over_keys[MOY_UI_OV_COUNT];
// Key `k` (MOY_UI_OV_*) given: its words `v` (a colour, 0 or 1, a wash's 0, 1
// or 2, a number, a pair, a quad; a tier's reader resolves a role's name and
// a Lua index) into *o, as every tier reads it; a text's key takes its span.
void moy_ui_over_put(moy_ui_over_t *o, int k, const int32_t *v);
void moy_ui_over_text(moy_ui_over_t *o, int k, moy_ui_span_t s);

typedef struct {
    uint32_t id;
    moy_ui_box_t b;                 // on screen, as drawn
    uint16_t flags;                 // STOP_* (moy_ui_api_int.h)
    uint8_t page;                   // the index of its page's stop, or 0xff
    uint8_t part;                   // a part: a held press with no page to drag stays its
    // A list's or a table's rows on its page (STOP_ROWS): the focused row
    // and row 0's top on screen, so a key step reveals its row at begin.
    int16_t row, top;
    uint8_t st;                     // the state bits it drew with (MOY_UI_ST_*)
    uint8_t bare;                   // a table's: the live pointer over its ground, on no row
                                    // or card a press would take (moy_ui_api_cursor's arrow)
    uint8_t quiet;                  // a press or a hover on it draws no mark: a text view's
    uint8_t cut;                    // placed while moy_ui_api_cut: inside its page's view, as stacked
    uint8_t open;                   // a field over O2_TYPING: focus coming onto it begins its edit
    int32_t gen;                    // the app's generation for what it draws in it
    uint32_t sig;                   // its record (kind, text, value), under the audit
} moy_ui_stop_t;

// The page a scroll region, a dialog's body or a popover's stands in, kept
// while it is open.
typedef struct {
    moy_ui_box_t page;
    int16_t y, scroll;
    int8_t keep;
    uint8_t stop, kind;             // kind: 1 a scroll region, 2 a dialog, 3 a popover
    int16_t used;                   // a dialog or popover: the body height it was laid out for
    int8_t snap, snap_more;         // the outer page's snap state (moy_ui_ctx_t's)
    int16_t snap_cut, snap_cap, snap_cue_h;
    int8_t snap_at, snap_older;
    int16_t snap_top;
} moy_ui_nest_t;
#define MOY_UI_API_NEST 2
// What a verb that opens a nest (ui.scroll, ui.text_view, ui.dialog,
// ui.popover) answers when MOY_UI_API_NEST are open already: it opens none
// and draws nothing, and each face reports it (Python and Lua raise, a
// compiled app's import answers -MOY_UI_DEEP).
#define MOY_UI_API_DEEP INT32_MIN

// A widget's kept state, by its id (the one per-widget store): what its
// kind keeps from frame to frame while the widget is drawn, freed the first
// frame it is not. A page is a page, a scroll region, a text view, a
// popover's or a dialog's body or a placed table's rows; a field's record
// is its edit's, the text the edit began from its instance's under the same
// id (moy_ui_api_table.c).
enum { MOY_UI_KEEP_PAGE = 1, MOY_UI_KEEP_LIST, MOY_UI_KEEP_SPLIT, MOY_UI_KEEP_FIELD };
typedef struct {
    uint32_t id;
    union {
        int32_t scroll;             // a page: its scroll
        int32_t row;                // a list: its current row
        int32_t div;                // a split: the divider a press took + 1, 0 none
    };
    union {
        int32_t rows;               // a page: its rows' height
        int32_t off1;               // a list: its view's offset + 1 (0: never drawn)
        int32_t grab;               // a split: where the press took it, along its axis
    };
    int16_t over;                   // a page: how far a scroll into view went past its rows
    int16_t foot;                   // a page: the hint band its foot gave up last frame
    int16_t peek;                   // a popover: the body height its cut peeks a row at, 0 none
    uint8_t seen;
    uint8_t kind;                   // MOY_UI_KEEP_*
    moy_ui_scroll_t sc;             // a page: its scroll's motion (a drag, a fling, a glide)
    // A page as its last pass drew it (moy_ui_api_shift_plan): the scroll it
    // drew at, the generation the app gave it, what it holds (MOY_UI_KD_*) and
    // the stops drawn inside it, from s0, sn of them.
    int32_t drawn, gen;
    uint8_t kd, s0, sn;
    // A field: its edit is in progress (its text other than the start), and
    // a cancel was taken over the frame drawn last (1) or gives the start
    // back this pass (2).
    uint8_t live;
    int16_t rh;                     // a placed table: its row height as it drew
    uint8_t rest;                   // a page under `follow`: it rests on its foot
    uint8_t cancel;
    // A field's edit mode: `edit` while its keys type, `begun` once its edit took the text it
    // began from, `opened` once an edit="open" field began one for this focus; `tail` its caret,
    // the bytes of its text after it; cx, cy the caret's steps the frame's keys owe it
    // (characters across, lines down).
    uint8_t edit, begun, opened;
    int8_t cx, cy;
    uint16_t tail;
    // A carousel's page (moy_ui_api_carousel): the row its keys and taps carry to the centre,
    // the row it rests on as the app was told, and a fling that came to rest at this frame's
    // begin (its glide to the nearest row starts unticked, as the frame after a fling's). `car`
    // its look (MOY_UI_LOOK_*); a shelf's, icons' or desk shelf's page (moy_ui_api_cells_grid)
    // keeps the card its keys are on as car_set and the card the app held current at its last
    // frame as car_row: only a move of the app's own current lands the keys there, so a page
    // whose app holds none keeps the card its keys moved to.
    uint8_t car, car_fling;
    int16_t car_row, car_set;
    uint32_t thumb;                 // a page or placed table: its thumb as it drew last, 0 none
} moy_ui_keep_t;

// A snapping page's units as its last pass placed them (moy_ui_ctx_t's
// tops): the page's id (0: the slot is free) and its units' tops, in its
// rows' pixels (0 its first row's top), ascending, MOY_UI_API_TOPS at most,
// from two views above its scroll on. A drag let go and a focus step settle
// its scroll onto one of them.
#define MOY_UI_API_SNAPS 3          // the snapping pages whose units a frame keeps
#define MOY_UI_API_TOPS 32          // the units kept a page
typedef struct {
    uint32_t id;
    uint8_t n;
    int16_t cue;                    // the band its foot keeps where its rows run on
    int16_t top[MOY_UI_API_TOPS];
} moy_ui_tops_t;

typedef struct {
    int16_t y, h;
    uint8_t page;
} moy_ui_cap_t;

// An INSTANCE of the toolkit: what its frames write outside their contexts --
// the kept rings and the faces (moy_ui_api_kept.c), the text views' rows,
// breaks and records (moy_ui_text.c), the blocks of fields
// (moy_ui_api_table.c) and the engine's counts. Each block is taken at its
// first use (PSRAM where the board has it) and moy_ui_inst_free gives them
// back. A context belongs to one instance (moy_ui_api_ctx_in): the shell,
// its Python apps and the console's run share the main one
// (moy_ui_inst_main), and a program that runs the toolkit on a task of its
// own makes its own, so no two tasks' frames write the same bytes.
//
// An instance holds none of the theme: the looks, the shape, the depth, the
// fonts and icons, the text view's word table and tones and the keycaps'
// input are the console's, written on its task between its frames, and
// every instance reads the live ones, so a theme change shows from the next
// frame it begins. The cart-text boundary is the sink's (moy_ui.h).
struct moy_ui_inst {               // moy_ui_inst_t (moy_ui_text.h)
    struct mua_kept_mem *kept;      // the kept rings and the faces' record
    uint32_t fc_owner, fc_ids;      // the context holding the faces' ticket, the last given
    struct moy_ui_text_mem *text;   // the text views' rows, breaks and records
    struct mua_block *blocks;       // MOY_UI_BLOCKS blocks of fields
    uint32_t block_tick, block_gen;
    uint32_t fades;                 // moy_ui_api_fades's count
    uint32_t audit_on, audit_fail;  // moy_ui_api_audit's switch and failures
    // The texts fields held when focus came onto them, or as Enter last
    // left them (moy_ui_api_cancel gives one back), each under its context
    // and its field's id: MOY_UI_API_EDITS at once (moy_ui_api_table.c).
    struct mua_edit *edits;
    uint32_t edit_seq;
    uint32_t owed;                  // moy_ui_api_owed's count
    uint8_t dims;                   // moy_ui_api_dims' bits
    // A popover's or a dialog's first frame drawn tall over what it
    // covers, kept until its body closes (moy_ui_api_pop.c), for the one
    // context drawing it.
    struct moy_ui_lent *lent;
};

// The main instance; an instance's size, for a face that owns it as bytes; a
// fresh one over `I` (no blocks taken); and its blocks given back, every
// context of it then to be reset before its next frame. A function here
// that takes an instance takes NULL as the main one.
moy_ui_inst_t *moy_ui_inst_main(void);
size_t moy_ui_inst_size(void);
void moy_ui_inst_init(moy_ui_inst_t *I);
void moy_ui_inst_free(moy_ui_inst_t *I);

// The table drawn last: moy_ui_ctx_t's `tbl`, owned by moy_ui_api_table.c.
typedef struct {
    // The table drawn last: row 0's top (scrolled), the rows' height and
    // count, the view they show in, and its picture column's x and side (0:
    // none).
    int16_t y0, rh, n, px, pw;
    moy_ui_box_t view;
} moy_ui_tbl_t;

// The table that carries its rows: moy_ui_ctx_t's `tc`, owned by moy_ui_api_table.c.
typedef struct {
    // The table that carries its rows (a placed table with a part, one a
    // context), as its last pass drew them: its id, its columns' geometry,
    // its view, scroll, row height and count, its current row and whether
    // it wore the focus mark, and the record (its cells, hashed) of rows
    // tc.r0 .. tc.r0 + tc.k - 1 (tc.k -1: none kept), so a frame draws a
    // row again only where its record or its marks changed.
    uint32_t id, geo;
    moy_ui_box_t view;
    int32_t off;
    int16_t rh, n, cur, r0, k, y0;
    uint8_t mark;
    uint32_t h[MOY_UI_API_TROWS];
} moy_ui_tc_t;

// The parts the table drawn last answers: moy_ui_ctx_t's `tp`, owned by moy_ui_api_table.c.
typedef struct {
    // The parts the table drawn last answers (moy_ui_api_table_part): its
    // id, the view its rows show in, row 0's top on screen, the row height,
    // the next row and the end, the part's x and width; whether one is open
    // (tp.row its row), its fades owed; row 0's top the last frame drew, and
    // the rows answered from the first that shows (bit i: row tp.v0 + i),
    // so the stops in a carried row's part are carried with it.
    uint32_t id;
    moy_ui_box_t view;
    int16_t y0, rh, i, e, x, w, n, row, py0, v0;
    int32_t off;
    uint8_t open, fade, carry;
    uint64_t ans;
    // ...where its rows lie side by side (tp.x1): row 0's left on screen
    // (scrolled), the room a part may draw past its cell (tp.spill), and the
    // part answered last's distance from the view's centre, in 256ths of a
    // row (moy_ui_api_table_dist)
    uint8_t x1;
    uint8_t keep, np;
    int16_t x0, spill;
    int32_t mid2, dist;       // twice the view's centre along the axis
} moy_ui_tp_t;

// The dialog drawn this frame: moy_ui_ctx_t's `dlg`, owned by moy_ui_api.c.
typedef struct {
    // The dialog drawn this frame: its id (0: none) and its card; whether
    // it stands over a held page (`wash` false) under the app's gen
    // (dlg.held), that gen, its buttons (a hash) and its body's foot on
    // screen. dw.*: the last frame's, and the frames it has stood as it is
    // (dw.n, a dialog's rows frame: moy_ui_api_shift_plan).
    uint32_t id;
    uint32_t last;              // the last dialog drawn's id, kept past the frame (its buttons' key)
    uint32_t open;              // the button a dialog opens on (its `focus`; 0: its first stop)
    moy_ui_box_t card;
    uint8_t held;
    uint8_t tight;              // a glass too short for its pads: their least (moy_ui_api_dialog)
    int8_t pick;                // the dialog button activated this frame, -1 none
    int32_t gen;
    uint32_t btn;
    int16_t foot;
    int16_t s0, s1;
} moy_ui_dlg_t;

// The dialog the last frame drew: moy_ui_ctx_t's `dw`, owned by moy_ui_api.c.
typedef struct {
    uint32_t id;
    moy_ui_box_t card;
    int32_t gen;
    uint32_t btn;
    uint8_t ok, n;
} moy_ui_dw_t;

// A snapping page's units: moy_ui_ctx_t's `snap`, owned by moy_ui_api.c.
typedef struct {
    // A page or scroll region under `snap` shows whole units only (a stacked
    // row; a group's caption with its first row; a list's row): snap.out the
    // row placed last is left out, snap.rows the next placement is a list
    // whose rows are its units, snap.more its rows ran on past its foot last
    // frame (so the foot keeps snap.cue_h for the "More below" cue);
    // snap.cut the screen row the left-out units at its foot start at, and
    // snap.cap a caption's top waiting for its first row (INT16_MIN none).
    int8_t on, out, rows, more;
    int16_t cut, cap, cue_h;
    // snap.at the tops slot the page open now records its units in (-1
    // none); under `follow`, snap.top the screen row a unit must start at
    // to show (the "Older messages" cue's band above it; INT16_MIN none)
    // and snap.older whether that cue draws there.
    int8_t at, older;
    int16_t top;
    moy_ui_tops_t tops[MOY_UI_API_SNAPS];
} moy_ui_snap_t;

// The cards look the table drawn next is (`on` 0: none; MOY_UI_LOOK_CAROUSEL, moy_ui_api_carousel,
// or MOY_UI_LOOK_SHELF or _ICONS, moy_ui_api_cells_grid): its geometry (moy_ui_api_carousel_geom's or
// moy_ui_api_cells_geom's), its band, and the row its app holds current. MOY_UI_LOOK_DESK is
// the carousel look on the desk class: its shelf (moy_ui_api_desk_shelf_geom's), drawn as cells.
// MOY_UI_LOOK_COLUMN is the column look's (moy_ui_api_column_geom's), drawn as cells.
enum { MOY_UI_LOOK_CAROUSEL = 1, MOY_UI_LOOK_SHELF, MOY_UI_LOOK_ICONS, MOY_UI_LOOK_DESK, MOY_UI_LOOK_COLUMN };
#define MOY_UI_CELLS_G 16
typedef struct {
    int8_t on;
    int16_t app, app_n;             // (app_n: a shelf's or icons' cards)
    int32_t g[MOY_UI_CELLS_G], band[4];
} moy_ui_car_t;

// ui.popover's: moy_ui_ctx_t's `pop`, owned by moy_ui_api_pop.c.
typedef struct {
    moy_ui_box_t card, prev, at;
    moy_ui_box_t view;          // the view its anchor lies in (`wash` "view")
    uint8_t gone;
    uint8_t back;               // the host's back took the popover: gone next frame
    uint8_t mid;                // it opened with nothing to hang from: centred
    uint8_t placed;             // it hangs from ui.at's rect
    uint32_t id;                // the popover drawn this frame (0: none)
    // Its body's cut while its rows lay out (content coordinates, 0: not
    // cut): the deepest row middle at or above it, and whether it already
    // falls well inside a row (a cut body peeks a row under its fade).
    int16_t cut, peek;
    uint8_t inside;
    // its first frame where the canvas cannot lend it the room to draw at
    // once (the instance's `lent`): laid out to size it, drawn the next
    uint8_t hide;
} moy_ui_pop_t;

// The next grid's spread: moy_ui_ctx_t's `spread`, owned by moy_ui_api_pop.c.
typedef struct {
    uint8_t cols, wrap;
    int16_t foot, top, margin;
} moy_ui_spread_t;

// The next label's text options: moy_ui_ctx_t's `txt`, owned by moy_ui_api_pop.c.
typedef struct {
    int8_t lines, centre, tone, role;
    uint8_t scale;                  // moy_ui_api_text_size's
    int16_t w;
} moy_ui_txt_t;

// A shift frame: moy_ui_ctx_t's `sh`, owned by moy_ui_api_host.c.
typedef struct {
    uint32_t id;
    moy_ui_box_t r;
    int16_t dy, rows, pics;
    int16_t in_dy;
    uint8_t plan, head, dlg;
    uint8_t in_tv;
    // R a page that holds the table carrying its rows, or a text view
    // (sh.in_id; tc.*): the view as the last frame drew it (sh.in) and its
    // move inside R (sh.in_dy, the host's second shift_last; R itself moves
    // by sh.dy, 0).
    // A stop drawn in one of its tables' parts moves with its row, so R's
    // stops are matched with the last frame's past them (fl.ci, fl.pi: the
    // next of each to match). sh.over: what the console drew over R after
    // the passes whose pixels R keeps (the FPS chip), which the floor draws
    // again; w 0: nothing.
    moy_ui_box_t over;
    uint32_t in_id;
    moy_ui_box_t in;
    // sh.in_tv: the view moving inside R is a text view's. sh.view: the
    // text view whose move inside R costs the canvas more to copy than its
    // rows to draw (`view_pays`): R holds still and the view's rows are the
    // floor, every one of them.
    uint32_t view;
} moy_ui_sh_t;

// A shift frame's floor: moy_ui_ctx_t's `fl`, owned by moy_ui_api_host.c.
typedef struct {
    uint8_t mute, top;
    uint8_t on, stage, n, unlike, dirty, susp, lost;
    uint8_t cast;                // the next draw casts a shadow past its box (a card's)
    uint8_t early;               // the floor is the pass's from its start (floor_reach)
    uint8_t s0, p0, pn;
    uint8_t ci, pi;
    uint32_t pend;
    // the app's parts this pass drew where the floor does not hold them (a
    // canvas draws its whole rect), as one box, w 0 none: what the engine
    // draws over them is drawn again (mua_thumb_track)
    moy_ui_box_t loose;
    moy_ui_box_t box[MOY_UI_API_FLOOR];
} moy_ui_fl_t;

// The kept ring's frame and the kept table's floor: moy_ui_ctx_t's `kf`,
// owned by moy_ui_api_kept.c.
typedef struct {
    // What the paints this context began left in the buffers a canvas
    // presents in turn -- its kept table and the parts `held` named
    // (moy_ui_api_held) -- lies in a ring the engine keeps for it outside
    // the context from its first kept table or `held` on (moy_ui_api_kept.c's
    // kept memory), so a context that keeps nothing carries none. kf.f is
    // the frame begun, kf.k the buffers (RETAINED_FRAMES, 0: nothing is
    // kept); kf.box the floor the kept table drawn last draws this frame, kf.i
    // the next rect moy_ui_api_table_floor answers, kf.held whether every
    // buffer holds the table as this frame draws it; kf.copy the floor's
    // rects the buffer the last frame painted holds as this frame draws
    // them (a bit each), kf.took those the app copied out of it
    // (moy_ui_api_table_copy), kf.ci the next one that answers; kf.sh the
    // move of the view kf.sv by kf.shift along its axis out of the buffer
    // the last frame painted (1 planned, 2 answered to the app:
    // moy_ui_api_table_shift).
    uint8_t k, n, i, held, copy, took, ci, sh;
    int32_t f, shift;
    moy_ui_box_t box[MOY_UI_KEPT_FLOOR], sv;
} moy_ui_kf_t;

typedef struct {
    uint32_t magic;
    int32_t in[MOY_UI_IN_LEN];
    int32_t last_key, last_ptr, last_typed;
    uint32_t focus;                 // the focused id, 0 none
    moy_ui_box_t focus_box;         // where it last drew
    char focus_name[MOY_UI_API_NAME];
    uint32_t act;                   // the id activated this frame
    uint32_t press;                 // the id the pointer went down on
    uint32_t drag_page;             // the page a drag scrolls
    uint32_t mid_page;              // the page a middle-button drag scrolls
    int16_t mid_y;
    int16_t tap_x, tap_y;           // where the activating tap was released
    moy_ui_box_t pa_box;            // the part answered last, where it stands (w 0: none)...
    moy_ui_box_t sp_hit[MOY_UI_API_DIVS];   // the dividers this frame's splits drew: what a press takes
    uint8_t sp_n;
    uint8_t pa_st;                  // ...its state bits (moy_ui_api_part_at)...
    uint8_t pa_none;                // ...and whether this pass leaves it undrawn (its out 0s)
    // The panes the last pass's splits cut (moy_ui_api_split_frame): a pane
    // a later split cut again (`sp_cut`, a bit a pane) is no pane of its own;
    // `sp_cur` the one a split's focus names (-1 none), `sp_held` whether a
    // divider was held. `sf_gen` the gen the last split frame was asked with.
    moy_ui_box_t sp_pane[MOY_UI_API_PANES];
    uint16_t sp_cut;
    uint8_t sp_pn, sp_held;
    int8_t sp_cur;
    int32_t sf_gen;
    int16_t press_x, press_y, drag_y;   // drag_y: the drag's last place along its axis
    uint8_t drag_x;                 // the drag scrolls across (a table's rows side by side)
    int16_t last_x, last_y;         // the pointer last frame
    int8_t step_x, step_y;          // the steps a key the focused stop keeps makes, signed
    int8_t carry_x, carry_y;        // a roll's steps past last frame's stops, walked next frame
    uint8_t keys, reveal, cls, fs;
    uint8_t win;                    // the page lies in a window's body (1), on a panel (2)
    uint8_t elsewhere;              // the keys are another surface's: no focus
    uint8_t tap;                    // the board's tap floor (moy_ui.h's MOY_UI_TAP)
    uint8_t app;                    // its buttons' row of app_buttons + 1, 0 none
    uint8_t n_prev, n_cur, has_at, gesture;    // gesture: 0 none, 1 down, 2 a scroll, 3 sideways
    moy_ui_stop_t prev[MOY_UI_API_STOPS], cur[MOY_UI_API_STOPS];
    moy_ui_keep_t keep[MOY_UI_API_KEEP];
    // The group captions drawn last frame and this one: where on screen, and
    // the page stop they lie on (a scroll into view keeps them whole).
    moy_ui_cap_t cap_prev[MOY_UI_API_CAPS], cap_cur[MOY_UI_API_CAPS];
    uint8_t n_cap_prev, n_cap_cur;
    moy_ui_box_t surface;           // what a page fills where ui.at does not place it
    moy_ui_box_t page;              // the content rect rows stack in
    moy_ui_box_t at;
    moy_ui_box_t at_view;           // the view ui.at's rect lay in: a scroll's, else the page
    moy_ui_box_t cut;               // the view placed draws clip to while cut_on (moy_ui_api_cut)
    uint8_t cut_on, cut_nest;       // cut_nest: the nest that view is of
    moy_ui_box_t over_band;         // the first page draw this frame that met the hints band, w 0 none
    int16_t y;                      // the row cursor, in content coordinates
    int16_t scroll;                 // the page's scroll
    int8_t page_keep;               // the page's kept state, or -1
    uint8_t page_stop;              // its stop, or 0xff
    uint8_t page_new;               // the page's first frame: no state was kept for it
    moy_ui_box_t reveal_box;        // a list row to keep in view next frame
    uint32_t reveal_id;             // the stop that row is in where it is not the focus, or 0
    uint32_t dup, dup_told;         // a duplicate id this frame (its hash), the last told
    uint16_t lost, lost_told;       // the stops past MOY_UI_API_STOPS this frame, the last told
    char dup_name[MOY_UI_API_NAME];
    // The open group (ui.group): its card's top in content coordinates, the
    // rows stacked on it, its last row's box and that row's marks, and the
    // marks of the row before it.
    int16_t grp_top;
    uint16_t grp_flags;
    uint8_t grp_open, grp_n, grp_any, grp_first;
    uint8_t grp_card;               // the open group is a desk's card (ui.group's `card`)
    moy_ui_box_t grp_last;
    // A focused button in the open group (due 1), and the row placed flush
    // under it (due 2, `cut`), which its ring's foot is drawn again over as the
    // group closes (moy_ui_button_ring).
    struct {
        moy_ui_box_t b, cut;
        moy_ui_button_t bt;
        int16_t kind, flags;
        int8_t interact;
        uint8_t due;
    } ring;
    // ui.icon's: the next row's icon, then the row's being drawn (an icon
    // set's slot and the glyph table's glyph, -1 none).
    int16_t icon_slot, icon_glyph, row_slot, row_glyph;
    // ui.menu's danger rows for the next menu: bit i, its row i (moy_ui_api_menu_danger)
    uint32_t menu_danger;
    // ui.scroll's and ui.dialog's open pages, innermost last.
    moy_ui_nest_t nest[MOY_UI_API_NEST];
    uint8_t n_nest;
    // The frame begun over a dialog's stops (MODAL: the others take no input);
    // a layout from a stale measure owes the next frame (OWE).
    uint8_t modal, owe;
    // The frame's begin moved the focus or a page's scroll (drawn by the
    // pass, owing nothing); the list or table whose key step begin revealed,
    // and the row it revealed.
    uint8_t moved;
    uint8_t jump;                   // the reveal is the app's focus move: no glide
    int16_t step_row;
    uint32_t step_rev;
    // A step that found no stop that way, outside a dialog: the frame's keys
    // went past the page's side (MOY_UI_EDGE_*; the shell walks focus onto
    // its bar from the top). `enter`: the side the next begin lands focus
    // from (moy_ui_api_enter), 0 none.
    uint8_t edge, enter;
    moy_ui_dlg_t dlg;
    uint32_t modal_from;            // the focus a dialog took
    uint32_t away;                  // the focus the page held when the keys went elsewhere
    int32_t typed;                  // the key a focused field takes this frame, 0 none
    int32_t typed_n;                // ...and how many times (a held key's repeats)
    // Q (-1) or E (1) pressed this frame outside a field: the tab row drawn
    // first steps back or on by it (ui.tabs), 0 none or taken.
    int8_t tab_step;
    // ui.popover's: the card drawn this frame and last (w 0: none), the
    // rect it hangs from, and whether this frame's input dismissed it (a
    // press outside the card drawn last, or Esc).
    moy_ui_pop_t pop;
    uint8_t tip_shown;              // ui.end drew a tooltip this frame
    // A popover's button row (its ui.buttons side by side, right-aligned
    // inside the card's padding): open while the buttons follow one
    // another, the row's top (content coordinates), the next button's x
    // from the row's left, and the row's width as this frame and the last
    // drew it, which places this frame's.
    uint8_t brow;
    int16_t brow_y, brow_x, brow_w, brow_was;
    // ui.grid's: open (2: placed by ui.at), its columns, the card next, the
    // first column's left edge and the columns' pitch, the pictures' size,
    // the top of the card row being laid out (content coordinates; a placed
    // grid's on screen) and a card row's height.
    uint8_t grid_open, grid_cols;
    uint16_t grid_i;
    int16_t grid_x, grid_pitch, grid_w, grid_h, grid_y, grid_row;
    moy_ui_box_t grid_at;
    // The card drawn last, its picture finished (corners, ring, a lifted
    // rim) by the next card or the grid's end, once the app drew into it.
    uint8_t fin_on, fin_flags;
    uint16_t fin_ground;
    moy_ui_box_t fin_pic, fin_content;
    int16_t fin_slot, fin_glyph;
    int8_t fin_tone;
    // what a row of a fitted grid (wrap 2) adds to its height for its
    // tallest card
    uint8_t grid_tall;
    // The next card's badge and tone (moy_ui_api_card_mark), the next
    // grid's spread (moy_ui_api_grid_spread) and the next label's text
    // options (moy_ui_api_text): each cleared once used and by begin.
    int16_t card_slot, card_glyph, card_blank, card_blank_glyph, card_lead, card_lead_glyph;
    int8_t card_tone;
    uint8_t grid_wrap;
    moy_ui_spread_t spread;
    moy_ui_txt_t txt;
    moy_ui_tbl_t tbl;
    moy_ui_tc_t tc;
    moy_ui_tp_t tp;
    moy_ui_dw_t dw;
    // The focused field's box last frame where this frame types into it (w
    // 0: none): its row joins a shift frame's floor.
    moy_ui_box_t typed_box;
    // The page's hint band this frame (h 0: none), which a wash leaves clear.
    moy_ui_box_t hint_band;
    // ui.tool's tooltip: the tool a resting pointer is over (w 0: none) and
    // its words, drawn over the page at ui.end.
    moy_ui_box_t tip_at;
    char tip[MOY_UI_API_TIP];
    // The way back the frame drawn last offers a front that takes the
    // host's back through the toolkit (moy_ui_api_way), and whether the
    // host took it since (moy_ui_api_way_taken answers it once).
    uint8_t way_on, way_taken;
    char page_title[MOY_UI_API_TIP];    // the top page's title this frame ("" none)
    // A shift frame (docs/history/scroll_and_text_2026-10.md §3.3): the region R that
    // moved (its keep's id and its box as the last frame drew it), the move
    // (dy, the shift_last a host makes: -1 x what the scroll moved), the plan
    // (MOY_UI_SHIFT_*) and whether R draws a fade at its head; then the
    // floor -- the rects inside R this pass draws, the rest of R being the
    // last frame's pixels moved -- once a host armed it (fl.on): where the
    // pass is in R (0 before it opens, 1 inside, 2 after), whether a stop
    // unlike the last frame's took the floor to R's foot, the rects that
    // still want their ground, the stops R holds, from fl.s0, and the last
    // frame's, from fl.p0, fl.pn of them; whether the pass drew over the
    // page (fl.dirty), how deep in an overlay it is (fl.susp) and whether
    // the floor ran out of rects (fl.lost). at_last: the stop placed last
    // was ui.at's.
    // A dialog's rows frame (sh.dlg) moves nothing: R is the last frame's
    // card and its drop, the floor the rows of its card's safe band
    // (dlg.s0..dlg.s1: the card's rows its rounded corners leave whole),
    // and its draws go through the floor alone. fl.mute: the dialog drawn
    // is not the one planned (its card, title, buttons or gen), so it draws
    // nothing this frame and owes the next. fl.top: something drew over a
    // dialog (a popover, a toast, a tooltip).
    moy_ui_sh_t sh;
    moy_ui_fl_t fl;
    uint8_t at_last;
    moy_ui_box_t pic_clip;          // the floor's rect the last card's picture draws through
    uint8_t pic_tbl;                // ...or the floor of the placed table drawn last as R
    // hover_off: no pointer held but one pressed over no stop it marks
    // (`press_bare`, from its press to the next), and no such stop under it
    // this frame or last (a quiet stop is none).
    uint8_t hover_off, press_bare;
    // what the last pass began under, which a shift frame's must equal
    moy_ui_box_t was_surface;
    uint16_t was_flags;
    uint8_t was_fs, was_hint;
    moy_ui_host_t host;             // its app host's (moy_ui_api_host_begin)
    moy_ui_kf_t kf;
    // The ticket of the engine's faces this context holds (moy_ui_api_slots;
    // 0: none), tp.np the parts a row of the table drawn last holds.
    uint32_t fc_id;
    // The instance it belongs to; the scope a table part's ids hash under
    // (0 outside a part); and whether the region closing draws no fade at
    // its foot.
    moy_ui_inst_t *inst;
    uint32_t scope;
    uint8_t no_foot;
    // The widgets that asked for kept state past the MOY_UI_API_KEEP ids this
    // frame (each drawn with none; 255 at most), and the count told last.
    uint8_t keep_lost, keep_lost_told;
    moy_ui_snap_t snap;
    moy_ui_car_t car;
    // The console's paste this frame (moy_ui_api_paste): the focused field
    // takes it; 0 none, and none once a frame begins.
    uint16_t paste_n;
    uint8_t paste[MOY_UI_API_PASTE];
    // PgDn 1, PgUp -1 at its press, else 0; and the text view with keys they
    // page, by its place among the frame's (from 1, 0 none): the one
    // focused, else the first. kv the last frame's, kv_next this frame's so
    // far (0x80: it is focused), kv_n the views drawn so far. Last, in the
    // struct's tail padding.
    int8_t page_y;
    uint8_t kv, kv_next, kv_n;
} moy_ui_ctx_t;

// A context's size, for a face that owns it as bytes; and a fresh one, of
// instance I (moy_ui_api_reset: the instance it was of, the main one for
// bytes that held no context).
size_t moy_ui_api_size(void);
void moy_ui_api_reset(moy_ui_ctx_t *c);
void moy_ui_api_reset_in(moy_ui_ctx_t *c, moy_ui_inst_t *I);
// A context the bytes at `p` hold (resetting them the first time, into
// instance I; moy_ui_api_ctx: the main one), or NULL where `n` is short or
// `p` misaligned.
moy_ui_ctx_t *moy_ui_api_ctx(void *p, size_t n);
moy_ui_ctx_t *moy_ui_api_ctx_in(moy_ui_inst_t *I, void *p, size_t n);

// A frame begins: `in` (MOY_UI_IN_LEN words, NULL none), the surface a page
// fills, its flags (moy_ui.h's MOY_UI_DESK: the desk's rows, else the
// handheld's; MOY_UI_WINDOW: the page lies in a window's body, so its ground
// is the window's; MOY_UI_ELSEWHERE: the keys are another surface's, so no
// stop holds focus this frame; and, in the bits from MOY_UI_APP_SHIFT, the row of the
// theme's app_buttons its buttons take plus one, 0 none, which only a shell
// app's host passes) and the font scale. Answers 1 when the frame OWES
// nothing: what its input changed, begin applied before the pass -- a focus
// moved, a page scrolled or a scroll's motion stepped (moy_ui_api_moved) --
// so the pass draws it and the frame after draws the same pixels. A frame
// owes the next for what applies after its pass: an activation, a typed
// key, a press or its release, a value a key stepped, a dismissed popover,
// a pointer that moved over the stops, a layout found stale or a reveal set
// during the pass (moy_ui_api_owes).
#define MOY_UI_APP_SHIFT 8
int moy_ui_api_begin(moy_ui_ctx_t *c, const int32_t *in, moy_ui_box_t surface, int flags,
                     int fs);

// ui.text_view(id, lines, o): a text area in rows (moy_ui_text.h), a scroll
// region of its own -- a drag scrolls it and its release coasts, the wheel
// steps it -- in ui.at's rect or stacked `rows` rows tall (0: the rest of
// the page). Its rows are the lines `L` gives: whole lines cut at its
// width, or wrapped there (`wrap`); in the mono face (or `font`, a loaded
// monospace font's id, where the caller gives one: 0 the mono role's; a
// cart's code draws in petme128 whatever it names), on a paper where
// `paper` is not -1 (the rect's ground in the `surface` token, its corners
// that radius, the rows inset from its top and foot by the radius or the
// text's inset, whichever is more, where the rect is that tall), coloured
// by `syntax`
// (MOY_UI_SYN_*: SGR escapes by default, a terminal's), numbered where
// `gutter`, a caret at `caret_line`, `caret_col` (-1: none). An editor's
// marks: a selection from (sel_r0, sel_c0) to (sel_r1, sel_c1) (sel_r0 -1:
// none), an error on line `err_line` (-1: none) underlined, its words
// `marks[0]` after it, the matches of the find query `marks[1]` (across
// case where `find_ci`), the current line's mark (`mark`: an editor's view,
// which keeps its caret's line in view itself and draws no fade at its
// foot), the columns cut off at the left (`left`; a change draws the view
// whole). `gen`, where
// the caller gives one (non-zero), names the lines' content: the wrapped
// rows' count is kept against it, else counted every frame. `top` (-1:
// none) aims the view at that line, its first row at the view's top: a
// glide there, or a jump on the view's first frame or a frame with no dt.
// Where `follow`, a view starts at its foot, and at its foot when the text
// grows it glides to the new foot (a log, a terminal). A host that aims the
// view before its frame begins (moy_ui_api_text_aim) lands it there instead,
// as that frame's shift. A frame draws only the rows that changed and
// moves the rest, as a scroll region's floor (§3.3 of
// docs/theme_and_shell_2026-11.md). out: the first line shown and the rows
// shown. Its content scrolls at most 32767 pixels: past that, the rows at
// the end are cut.
//
// A view keeps a record by its id (moy_ui_text.h's MOY_UI_TEXT_VIEWS, the
// views of every context of an instance together, the least recently drawn
// given up first): the
// rows it drew, which it plans the next frame against, and where they lay,
// which moy_ui_api_text_at reads. Its scroll is its region's, kept by the
// context like every page's.
typedef struct {
    void *src;
    int32_t n;
    const uint8_t *(*get)(void *src, int32_t i, size_t *len);
} moy_ui_lines_t;
enum {
    MOY_UI_TXO_ROWS = 0, MOY_UI_TXO_WRAP, MOY_UI_TXO_SYNTAX, MOY_UI_TXO_FOLLOW,
    MOY_UI_TXO_GUTTER, MOY_UI_TXO_CARET_LINE, MOY_UI_TXO_CARET_COL,
    MOY_UI_TXO_SEL_R0, MOY_UI_TXO_SEL_C0, MOY_UI_TXO_SEL_R1, MOY_UI_TXO_SEL_C1,
    MOY_UI_TXO_ERR_LINE, MOY_UI_TXO_FIND_CI, MOY_UI_TXO_LEFT, MOY_UI_TXO_MARK,
    MOY_UI_TXO_GEN, MOY_UI_TXO_TOP, MOY_UI_TXO_FONT, MOY_UI_TXO_PAPER, MOY_UI_TXO_FACE,
    MOY_UI_TXO_KEYS, MOY_UI_TXO_LEN
};
// MOY_UI_TXO_FACE's: the mono face's cells (the default), or prose in the ui
// face -- each line a paragraph broken at word breaks across the view, its
// lines a line's pitch apart and paragraphs half a line more; no syntax,
// caret, selection, gutter or mark; moy_ui_api_text_at, _aim and _reveal
// answer 0 for it; `top` and `gen` name paragraphs. MOY_UI_TXO_PAPER 0 or more
// lays its prose on a part's well (moy_ui_well), in from the page's sides,
// its paragraphs one under the next and its foot fading where they run on.
enum { MOY_UI_TXF_MONO = 0, MOY_UI_TXF_UI = 1 };
// MOY_UI_TXO_KEYS 1: a view whose rows run past it is a focus stop (no
// ring): Up and Down scroll it a line while it has rows that way, then step
// focus on as a list's ends do; PgUp and PgDn scroll it a page less a line,
// where it is focused or, focus on no such view, it is the first drawn.
// The options' defaults, in MOY_UI_TXO_* order: what a face that takes
// fewer of them fills the rest with.
#define MOY_UI_TXO_DEFAULTS {0, 0, MOY_UI_SYN_SGR, 0, 0, -1, -1, -1, 0, -1, 0, -1, 0, 0, 0, 0, -1, 0, -1, 0, 0}
// Answers 0, or MOY_UI_API_DEEP.
int32_t moy_ui_api_text_view(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t id,
                             const moy_ui_lines_t *L, const int32_t *opt,
                             const moy_ui_span_t *marks, const moy_ui_over_t *o,
                             int32_t out[2]);
// The text cell under (px, py) in view `id` as its last pass drew it: its
// line and column into out, 1; 0 where the point lies off its rows (a
// column left of the text is 0, past a row's end that row's end where it
// wraps, else the column the point is over).
int moy_ui_api_text_at(const moy_ui_ctx_t *c, moy_ui_span_t id, int px, int py,
                       int32_t out[2]);
// Before a frame begins: view `id` shows line `line` first (-1: its foot,
// where it stood at its foot and its `lines` grew), so the move is that
// frame's shift; its pass, given the same `top`, moves nothing. 0 where it
// did not move: a view new to the context, a wrapped one, one held by a
// finger, or one already there (its pass aims it: a glide).
int moy_ui_api_text_aim(moy_ui_ctx_t *c, moy_ui_span_t id, int32_t line, int32_t lines);
// Before a frame begins: view `id`, showing `L`, moves only as far as its
// rows need to show line `line`'s row that holds column `col` (a caret's),
// or with `col` -1 shows that line first, its wrapped rows counted as its
// last pass laid them; the move is that frame's shift. 0 where it did not
// move: a view new to the context, one held by a finger, or one that shows
// it already.
int moy_ui_api_text_reveal(moy_ui_ctx_t *c, moy_ui_span_t id, const moy_ui_lines_t *L,
                           int32_t line, int32_t col);
// Rows y0..y1 of view `id` were drawn over after its pass this frame (an
// overlay the pass does not draw): its next frame draws them again.
void moy_ui_api_text_cover(const moy_ui_ctx_t *c, moy_ui_span_t id, int y0, int y1);
// The colour indices the syntax classes take under the live theme
// (MOY_UI_TT_KEYWORD .. MOY_UI_TT_BUILTIN, the theme's code_* content roles;
// TT_TEXT the code's ink), -1 where a role falls back to a token.
void moy_ui_text_tones(const int16_t tones[6]);

// The verbs (§1). `o` may be NULL. Text is a span.
void moy_ui_api_page(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t title,
                     const moy_ui_over_t *o, moy_ui_box_t *content);
// A host test's tap on the verbs that put words on the page: each label, value row, group
// caption, button, hints band, icon and slider as its verb is called, with its texts (`b` NULL
// where it has one; a band's items NUL-separated; a slider's `b` "LO HI STEPS", a progress
// row's "V HI"), for a label
// the face role its text options ask (-1: none), for an icon whether the theme's set draws it.
// NULL, the default and a board's only value, taps nothing.
enum { MOY_UI_SAID_LABEL = 1, MOY_UI_SAID_INFO, MOY_UI_SAID_LINK, MOY_UI_SAID_GROUP,
       MOY_UI_SAID_BUTTON, MOY_UI_SAID_HINTS, MOY_UI_SAID_ICON, MOY_UI_SAID_SLIDER,
       MOY_UI_SAID_PROGRESS };
typedef void (*moy_ui_said_fn)(int verb, const uint8_t *a, size_t an, const uint8_t *b, size_t bn,
                               int role);
void moy_ui_api_said(moy_ui_said_fn fn);
void moy_ui_api_label(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t text,
                      const moy_ui_over_t *o);
// `kind` a button kind's index (moy_ui_button_kinds: normal, primary, tonal,
// danger, toggle), or MOY_UI_BUTTON_BAR, the shell's bar item
// (moy_ui_bar_item: no kind of the style's, no theme leaves); an unknown one
// draws as normal.
#define MOY_UI_BUTTON_BAR 5
int moy_ui_api_button(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t label, int kind,
                      const moy_ui_over_t *o);
int moy_ui_api_toggle(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t label, int on,
                      const moy_ui_over_t *o);
int32_t moy_ui_api_slider(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t label,
                          int32_t v, int32_t lo, int32_t hi, const moy_ui_over_t *o);
// A stepper (moy_ui_stepper): `value` between a back and a forward chevron,
// each greyed where `can` lacks its bit (1 back, 2 forward), its words `ink`
// (MOY_UI_TONE_INK or MOY_UI_TONE_DIM). Stacked on a page it stands its
// natural width centred on its row; ui.at's rect is its own, the chevrons at
// its ends. Left and right are its own while focused, activation steps
// forward and a tap steps the half it lands in. Answers -1 or 1 the frame it
// steps a way `can` allows, else 0; its box (x, y, w, h) in `box`.
int moy_ui_api_stepper(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t value, int can,
                       int tone, const moy_ui_over_t *o, int32_t box[4]);
// `items` NUL-separated in `len` bytes; `cur` from 0, -1 none. Answers the new cur.
int32_t moy_ui_api_list(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t label,
                        const uint8_t *items, size_t len, int32_t cur, const moy_ui_over_t *o);
// A group (§1): `caption` heads a card the rows stacked after it sit on,
// until the next group or a caption of length 0, which ends it.
void moy_ui_api_group(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t caption,
                      const moy_ui_over_t *o);
// A row with a value at its right: `kind` MOY_UI_V_INFO (no stop) or
// MOY_UI_V_LINK, which answers true the frame it is activated.
int moy_ui_api_value(moy_ui_ctx_t *c, const moy_ui_sink_t *s, int kind, moy_ui_span_t label,
                     moy_ui_span_t value, const moy_ui_over_t *o);
// A link as a list's two-line row (moy_ui_row2: `two`'s lead, tag, mark,
// value, sub and count; its title `label`), a stop of its own: true the
// frame it is activated.
int moy_ui_api_value2(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t label,
                      const moy_ui_row2_t *two, const moy_ui_over_t *o);
// A choice of `n` options with `cur` (from 0, -1 none) current: `kind`
// MOY_UI_V_CYCLE, MOY_UI_V_SEG and MOY_UI_V_TABS (a tab row: its options
// from the left, its label only its id) take `opts` NUL-separated,
// MOY_UI_V_SWATCH `n` colours (0xRRGGBB, little-endian words). Left and right
// are its own while focused (a cycle wraps); activation takes the next
// option, a tap the one tapped. Answers the new cur.
int32_t moy_ui_api_choice(moy_ui_ctx_t *c, const moy_ui_sink_t *s, int kind, moy_ui_span_t label,
                          const uint8_t *opts, size_t len, int32_t cur, const moy_ui_over_t *o);
// A pictures row (MOY_UI_V_PICS, moy_ui_pics_tile): its label, then `n` tiles at its right,
// `cur` (from 0, -1 none) on the selection's plate. Left and right are its own while focused
// and wrap; activation takes the next tile, a tap the one tapped. The caller draws each tile's
// picture over its plate (moy_ui_api_pics_tile, clipped by moy_ui_api_card_clip); `o`'s gen is
// the pictures' (a shift frame draws the row again where it moved, none: no shift frame).
// out: the row's box (0 wide where a shift frame leaves it as it moved) and its state bits.
// Answers the new cur.
int32_t moy_ui_api_pics(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t label, int n,
                        int32_t cur, const moy_ui_over_t *o, int32_t out[5]);
// Tile i of a pictures row of `n` whose box is row[0..3] (moy_ui_api_pics' out).
void moy_ui_api_pics_tile(const moy_ui_ctx_t *c, const int32_t row[4], int n, int i,
                          int32_t out[4]);
// Keycap hints (`items` NUL-separated pairs of an action or keys and what it
// does, moy_ui_hints) in a band at the page's foot, which its rows then stack
// above; ui.at places them instead; `hint` the status words it leads with
// (moy_ui_hints_status). Under the input touch there is no band and a ui.at
// before it is spent.
void moy_ui_api_hints(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const uint8_t *items, size_t len,
                      const moy_ui_over_t *o);
// The width those hints take with the input in use, their margin at either
// end included (0 under touch): what a band placed to end where they do is.
int moy_ui_api_hints_w(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const uint8_t *items,
                       size_t len);
// A row of keycap hints (moy_ui_hints' pairs, `items` NUL-separated) in ui.at's
// rect, else a band at the row cursor: the last `tail` pairs at the row's end,
// a margin in from it, the others laid from its start in order. Where they run
// into the tail, the pairs whose bits `drop` holds go first, the last first,
// then the others, the last first. No stops: answers the pair a press landed
// on this frame (the tail's counted after every other pair), else -1.
// out (`cap` words, NULL none): the row's box, then each pair's x0 and x1 in
// that order (both 0 where it did not draw).
int moy_ui_api_hint_row(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const uint8_t *items, size_t len,
                        int tail, uint32_t drop, int32_t *out, int cap);
// The next row (a label, info, link, cycle, seg, swatch picker, toggle,
// slider or progress) draws icon `name` before its label: the live icon
// set's slot of that name (moy_ui_icon_slot), else the glyph table's.
// Answers whether either names it.
int moy_ui_api_icon(moy_ui_ctx_t *c, moy_ui_span_t name);
// A row showing `v` of `hi` done as a bar and its percent at the right; no stop.
void moy_ui_api_progress(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t label, int32_t v,
                         int32_t hi, const moy_ui_over_t *o);
// A table (§1): `cols` its headers and `cells` its rows' cells row by row
// (both NUL-separated), `cur` the current row (from 0, -1 none), which
// follows its focus. out[0] the new cur, out[1] 1 the frame a current row is
// opened (Enter on it, or a tap on the row already current).
void moy_ui_api_table(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t label,
                      const uint8_t *cols, size_t cols_n, const uint8_t *cells, size_t cells_n,
                      int32_t cur, const moy_ui_over_t *o, int32_t out[2]);
// A scroll region (§1): `id` begins one in ui.at's rect (else the page's
// room below its rows), whose stacked rows scroll in it; an id of length 0
// ends it. Answers 0, or MOY_UI_API_DEEP.
int32_t moy_ui_api_scroll(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t id,
                          const moy_ui_over_t *o);
// A text field (§1) editing the `len` bytes at `buf` (`cap` its room): a
// stop the keys move past until Enter, A, a tap or a click begins its edit
// (over O2_TYPING, focus coming onto it, or the app's moy_ui_api_focus
// naming it, begins one, and Enter leaves it open); while it edits every
// key types at its caret, the directions move the caret (left and right a
// character, up and down to the start and the end), Enter ends it (Esc,
// moy_ui_api_cancel, gives back the text it began from) and focus stays.
// Answers the new length, plus MOY_UI_FIELD_DONE the frame Enter is pressed
// in it.
#define MOY_UI_FIELD_DONE 0x10000
int32_t moy_ui_api_field(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t label,
                         uint8_t *buf, size_t cap, size_t len, const moy_ui_over_t *o);
// A dialog (§1): `title` begins a modal card centred on the surface, its
// `buttons` (NUL-separated, the last of `kind`, the others normal) at its
// foot, its body the rows stacked until a title of length 0 ends it. Answers
// the button activated this frame (from 0), -1 none, or MOY_UI_API_DEEP; the
// end answers -1. Its first frame shows it at the size it rests at: drawn as
// tall as the surface lets it, its body laid out in that room, and moved to
// its place when the end closes it (as a popover's first frame, the
// instance's `lent`). A body taller than its room is cut to it, a fade at
// each edge its rows run on past; a drag scrolls it, and so does an arrow
// where no stop lies that way. Where the room leaves the body under three
// rows at the card's pads, the pads are their least (`dlg.tight`).
// Its wash is the surface, less the page's hint band at its foot; with the
// override `wash` false it draws none, where the page under it was washed
// already (`moy_ui_api_wash`, the page an app holds under its dialog).
int32_t moy_ui_api_dialog(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t title,
                          const uint8_t *buttons, size_t len, int kind, const moy_ui_over_t *o);
// Washes what a dialog begun now would: the surface, less the page's hint
// band at its foot.
void moy_ui_api_wash(moy_ui_ctx_t *c, const moy_ui_sink_t *s);
// The box that wash covers (moy_ui_scrim_io washes it over another frame).
moy_ui_box_t moy_ui_api_wash_box(const moy_ui_ctx_t *c);
// A popover (§1): `id` begins a card hung under ui.at's rect (else under the
// stop that holds focus as it opens), above it where the surface has no room
// below, `w` wide (0: the rect's width), its body the rows stacked until an
// id of length 0 ends it. While it is drawn nothing outside it takes input,
// as under a dialog. Answers 1, or 0 the frame a press outside the card or
// Esc dismissed it, or MOY_UI_API_DEEP; the end answers 0.
#define MOY_UI_KEY_ESC 27
int moy_ui_api_popover(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t id, int w,
                       const moy_ui_over_t *o);
// A menu (§1): its caption (`label`; of length 0 none, and then a rule when
// rows sit above it in its page), then a row a stop per item of `items`
// (NUL-separated, `len` bytes), the icon named at the same place in `icons`
// (NUL-separated, `ilen` bytes; an empty name, or none, no icon) before its
// label. An item's id is its text. Stacked on the page, or from ui.at's
// rect's top left across its width. Answers the item activated this frame
// (from 0), -1 none. The rows moy_ui_api_menu_danger named last are danger
// rows: their label and icon in the theme's menu danger ink (its look's
// `danger_ink`), else the danger buttons' ink.
int32_t moy_ui_api_menu(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t label,
                        const uint8_t *items, size_t len, const uint8_t *icons, size_t ilen,
                        const moy_ui_over_t *o);
// The next ui.menu's danger rows (a verb that destroys: Delete): bit i its row i.
void moy_ui_api_menu_danger(moy_ui_ctx_t *c, uint32_t rows);
// The Python face's options the override block does not carry, each for the
// next call of its verb: a label's text (`lines` its most, 0 one unwrapped;
// `centre` 1 centred, 2 in from the page's edges as a group's caption is, 3
// on a `sunk` inset across the row, the text inside its padding, 4 each line
// at the row's end; a label stacked in an open group lies on its card, its
// text a row's pad in from the card's edges;
// `tone` MOY_UI_TONE_*; `role` a font role, -1 the label's own),
// a card's badge (icon `badge`, empty none), tone and blank picture (icon
// `blank` on a tinted tile, empty none: moy_ui_card_blank), a grid's spread (its
// `cols` columns spread across its rect, the gaps taking the rest; `foot`
// the card's foot under its picture, `top` the room over its first row and
// `margin` its rect's at either side, in pixels at the scale, 0 the style's;
// `wrap` 1 its cards' titles take two lines where their foot holds them,
// 2 each row also grows by the second line where a card's title takes it;
// `cols` 0 keeps the columns the grid fits, its `foot` and `top` still
// taken; `foot` below 0 is none).
void moy_ui_api_text(moy_ui_ctx_t *c, int lines, int centre, int tone, int role);
// The next label's size, with its text options: its text at the whole scale
// `scale` (0: the sink's) and at most `w` pixels wide from where it starts
// (0: its row's width), a measure of prose or a display line.
void moy_ui_api_text_size(moy_ui_ctx_t *c, int scale, int w);
void moy_ui_api_card_mark(moy_ui_ctx_t *c, moy_ui_span_t badge, int tone,
                          moy_ui_span_t blank);
// The next card's title's icon (`icon`, empty none): drawn before its title,
// the two centred under its picture as one.
void moy_ui_api_card_lead(moy_ui_ctx_t *c, moy_ui_span_t icon);
void moy_ui_api_grid_spread(moy_ui_ctx_t *c, int cols, int foot, int top, int margin,
                            int wrap);
// A group with no caption (ui.group's `card`): its rows on its card, from
// the page's next row, until a group call ends it.
void moy_ui_api_group_card(moy_ui_ctx_t *c, const moy_ui_sink_t *s);
// A group with no caption whose rows a rule parts, as a captioned group's
// (ui.group's `rules`): from the page's next row, until a group call ends it.
void moy_ui_api_group_rules(moy_ui_ctx_t *c, const moy_ui_sink_t *s);
// Where a group is open, the page's next `h` pixels a row of it the caller
// draws placed: the page's cursor under it and its rule (on the handheld its
// card's band) drawn. 0 where none is open, and nothing done.
int moy_ui_api_group_row(moy_ui_ctx_t *c, const moy_ui_sink_t *s, int h);
// A card's plate at ui.at's rect, the rows it holds placed on it by the caller
// (a split's cell of ui.group's `card`): rounded and filled, on the desk a ring.
void moy_ui_api_card_at(moy_ui_ctx_t *c, const moy_ui_sink_t *s);
// An empty page's head (ui.empty) at `at`'s rect, else the page's next row:
// the icon on its disc, the title and the lines (NUL-separated), centred.
// Its foot's y, where the page's verbs go.
// ui.note(icon, lines): a note on the page (moy_ui.h's moy_ui_note), a
// stacked row (else at `at`'s rect's top) and no stop; `icon` "warn" in the
// danger label tone. The y under it.
int moy_ui_api_note(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t icon,
                    const uint8_t *lines, size_t n);
// The height a note of `lines` (as moy_ui_api_note takes them) takes at width `w`.
int moy_ui_api_note_h(const moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t icon,
                      const uint8_t *lines, size_t n, int w);
int moy_ui_api_empty(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t icon,
                     moy_ui_span_t title, const uint8_t *lines, size_t n);
// A chat's bubble (ui.bubble, moy_ui.h's moy_ui_bubble) at `at`'s rect's
// top, across its width, else stacked on the page inside its gutters, a
// stop: `opt` its options as words in MOY_UI_BBO_* order (`n` of them, the
// rest their defaults: side 0 "in", signal -1 none, tone 0, max 75
// hundredths, lines 4, anchor 0). out: the bubble's x, y and w, the
// block's h (the bubble and its status line: a popover hung from it clears
// the line) and the state bits, MOY_UI_ST_CUT where its text was cut. Stacked bubbles stand
// 4 pixels apart at the scale, 6 on the desk.
enum { MOY_UI_BBO_SIDE, MOY_UI_BBO_SIGNAL, MOY_UI_BBO_TONE, MOY_UI_BBO_MAX, MOY_UI_BBO_LINES,
       MOY_UI_BBO_ANCHOR, MOY_UI_BBO_WORDS };
#define MOY_UI_ST_CUT 16
void moy_ui_api_bubble(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t text,
                       moy_ui_span_t head, moy_ui_span_t status, const int32_t *opt, int n,
                       const moy_ui_over_t *o, int32_t out[5]);
// A month (ui.month) at `at`'s rect, else stacked on the page (its weeks
// tightening into what the page shows under its head): `title`,
// the weekdays' initials `days`, `n` days from column `first` (0 Monday),
// `today` marked (0 none); on the desk and under touch its head carries the
// two chevrons. -1 or 1 the frame a press lands on one, else 0.
int moy_ui_api_month(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t title,
                     moy_ui_span_t days, int first, int n, int today);
// A toast (ui.toast) over the foot of `at`'s rect, else of the page: the
// `check` icon, else `kind`'s (the icon slot it names), and `text`; `flat`
// with no soft shadow. Its pill's box in out[4].
void moy_ui_api_toast(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t text,
                      moy_ui_span_t kind, int flat, int32_t out[4]);
// A card grid (§1): `id` begins one whose cards' pictures are w x h, as
// many columns as the row holds, the grid's rows stacking on the page (or
// from ui.at's rect's top left, across its width); an id of length 0 ends it.
void moy_ui_api_grid(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t id, int w, int h,
                     const moy_ui_over_t *o);
// A card in the open grid: `title` (its id) and `sub` under its picture, the
// current mark where o->current. out: the picture's x, y, w, h -- the app
// draws into it before its next ui call -- and the state bits (§5).
void moy_ui_api_card(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t title,
                     moy_ui_span_t sub, const moy_ui_over_t *o, int32_t out[5]);
// The table drawn last this frame (ui.table): out row 0's top (scrolled),
// the rows' height, the view's x, y, w and h, the picture column's x and
// side, where an app draws a row's own picture over its cell; 0 where that
// table has no picture column or none was drawn.
int moy_ui_api_table_rows(const moy_ui_ctx_t *c, int32_t out[8]);
// The table drawn last, its pictures drawn: the fades at the edges its rows
// run on past, again over its picture column, so a cut row's picture fades
// with its row (Files' covers).
void moy_ui_api_table_pics(moy_ui_ctx_t *c, const moy_ui_sink_t *s);
// The next part of the table drawn last (one given o->part) this frame
// draws: its row (from 0), its cell's x, y, w and h into out[0..3] and what
// shows of it (the clip the app draws its part under) into out[4..7], the
// ids of the verbs drawn until the next call scoped by the row; -1 after
// the last, the table's fades drawn over its parts. A frame drawn whole
// answers the rows that show; a shift frame only the rows its floor holds
// (those that entered, and those whose cells or marks changed): what an
// app draws in a row's part is a function of that row's cells.
int32_t moy_ui_api_table_part(moy_ui_ctx_t *c, const moy_ui_sink_t *s, int32_t out[8]);
// The part moy_ui_api_table_part answered last: its cell's centre's distance
// from its view's centre along the rows' axis, in 256ths of a row, negative
// before it (above, or on the left); 0 where none was answered.
int32_t moy_ui_api_table_dist(const moy_ui_ctx_t *c);
// The table drawn last, its parts not yet all answered: out[0] 1 where it holds the focus
// (the keys this surface's), out[1] its scroll along its rows' axis, out[2] 1 while its view
// moves (a drag, a fling or a glide).
void moy_ui_api_table_state(moy_ui_ctx_t *c, int32_t out[3]);
// A carousel (ui.cards look "carousel", the handheld home's band): its geometry in band `b`
// (x, y, w, h) at font scale `fs` for tiles at most `side` px a side, the pitch 14 px more at
// the scale. out[0]
// the side a tile rests at off the centre (the largest that shows a whole cover at a clean
// scale, moy_ui_api_clean_side, and leaves the caption its room), [1] the pitch, [2] the
// tiles' centre line, [3] the title's top, [4] its line, [5] its scale (16 px at the font
// scale, at least that scale), [6] the sub line's top, [7] its line, [8] the centre tile's
// side at rest (twice [0]), [9] the room kept over the centre tile for its focus mark.
void moy_ui_api_carousel_geom(int fs, const int32_t b[4], int side, int32_t out[10]);
// A carousel's tile for row `i` at scroll `offset` (geometry `g`, band `b`): its side a function
// of its distance from the centre alone, `g[0]` at a pitch or more, rising to `g[8]` at the
// centre, each other tile pushed out by its share of what the centre grew; out its x, y, w, h.
void moy_ui_api_carousel_tile(const int32_t g[10], const int32_t b[4], int32_t offset, int i,
                              int32_t out[4]);
// The row of `n` whose tile holds (x, y) at scroll `offset`: of the tiles that hold it, the
// one drawn last (the larger over the smaller, the centre's over a neighbour its size); -1
// none.
int moy_ui_api_carousel_at(const int32_t g[10], const int32_t b[4], int32_t offset, int n, int x,
                           int y);
// A carousel's row of tiles, `n` rows of `cells` (each row's key), in band `b` under geometry
// `g`: one stop, a table of parts side by side that snaps, the motion the handheld home's
// (moy_ui.h's slide): left and right (a held key's repeats, the wheel's notches) carry the row
// a card from where its glide is going, a drag past the slop moves it with the finger and a
// release flings it, a row come to rest between two cards slides to the nearest, and a tap on
// a tile slides that tile to the centre; Enter, or a tap on the centre's tile at rest, opens.
// `cur` the row the app holds current, which the row lands on at once where it moves while
// the row rests. out[0] the row it rests on (its last while it moves), out[1] 1 where it
// opened that row, out[2] its scroll, out[3] its motion (MOY_UI_SCROLL_DRAG, _FLING,
// _GLIDE), out[4] 1 where it holds the focus. Its parts answer as a table's.
void moy_ui_api_carousel(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t id, const int32_t b[4],
                         const int32_t g[10], const uint8_t *cells, size_t cells_n, int32_t cur,
                         int32_t out[5]);
// A home grid of cards (ui.cards look "shelf" or "icons", MOY_UI_LOOK_SHELF or _ICONS): its
// geometry in band `b` (x, y, w, h) at font scale `fs`, on the desk's metrics where `desk`,
// `u` glass pixels a pixel (a doubled desk's 2). A shelf: cards of the clean side a
// carousel neighbour takes (the desk's: the whole cover) in the rows the band holds, in
// columns that scroll across, spaced so the last column on the glass stands cut by a third or
// more, each card's title under it. Icons: tiles in as many columns as the band holds, in
// rows that scroll down; on the desk each named under it, on the handheld the card the keys
// are on named in a caption band along the band's foot. out[MOY_UI_CELLS_*].
enum { MOY_UI_CELLS_SIDE, MOY_UI_CELLS_R, MOY_UI_CELLS_X0, MOY_UI_CELLS_Y0, MOY_UI_CELLS_PX,
       MOY_UI_CELLS_PY, MOY_UI_CELLS_ROWS, MOY_UI_CELLS_COLS, MOY_UI_CELLS_TITLE_DY,
       MOY_UI_CELLS_TITLE_W, MOY_UI_CELLS_GROW, MOY_UI_CELLS_CAP_H, MOY_UI_CELLS_VIEW_H,
       MOY_UI_CELLS_ACROSS, MOY_UI_CELLS_DESK, MOY_UI_CELLS_LOOK };
// (TITLE_DY 0: no title under a card; CAP_H the caption band's height, 0 none; VIEW_H the
// band's height over the caption; ACROSS 1 where the cells scroll across.)
void moy_ui_api_cells_geom(int look, int fs, int desk, int u, const int32_t b[4],
                           int32_t out[MOY_UI_CELLS_G]);
// The column look's geometry (ui.cards look "column", MOY_UI_LOOK_COLUMN) in band `b` at font
// scale `fs` for `n` cards whose widest title is `title_w` pixels: tiles `side` across on rows
// `pitch` apart (or further, where a tile, its title's line and 6 of the 44 under it need
// more), down the band's left edge from 18 of the 44 under its top (12 of 40 on the handheld) and
// on into further columns, each title under
// its tile 2 of the 44 below it, the columns as wide as the widest title (as wide as the band
// leaves them, the titles cut to it) and their centres 54 of the 44 in from the band's edge or
// further where a title needs it. Where the columns would run past the band's right edge the
// tiles shrink, an eighth at a time and the rows and margins with them, until they fit or
// reach MOY_UI_COLUMN_MIN. out[MOY_UI_CELLS_*], ACROSS 1.
#define MOY_UI_COLUMN_MIN 12
void moy_ui_api_column_geom(int fs, int desk, int side, int pitch, int title_w, int n, const int32_t b[4],
                            int32_t out[MOY_UI_CELLS_G]);
// The cells' content along their scroll for `n` cards (its margins either side), and the
// scroll that keeps card `i` with its margin in view from scroll `off`.
int32_t moy_ui_api_cells_extent(const int32_t g[MOY_UI_CELLS_G], const int32_t b[4], int n);
int32_t moy_ui_api_cells_reveal(const int32_t g[MOY_UI_CELLS_G], const int32_t b[4], int n, int i,
                                int32_t off);
// Card `i`'s box at scroll `off` (x, y, w, h); the card whose box or title holds (x, y), -1
// none.
void moy_ui_api_cells_tile(const int32_t g[MOY_UI_CELLS_G], const int32_t b[4], int32_t off, int i,
                           int32_t out[4]);
int moy_ui_api_cells_at(const int32_t g[MOY_UI_CELLS_G], const int32_t b[4], int32_t off, int n,
                        int x, int y);
// The cells' `n` cards (cells: each card's key, NUL after each, the table's rows a shelf's
// columns or the icons' rows, its last row's cards to come empty), one stop: the arrows step the card the keys are on across the grid and the
// view lands where it shows it with its margin, the wheel's notches step it too (Shift's
// across), a drag past the slop scrolls the view and a release flings it, a tap on a card
// makes it current and opens it, Enter opens the current card. `cur` the card the app holds
// current, which the view lands on where the app moves it. out[0] the current card, out[1]
// 1 where it opened it, out[2] the scroll, out[3] the motion (MOY_UI_SCROLL_DRAG, _FLING),
// out[4] 1 where it holds the focus. Its parts answer as a table's.
void moy_ui_api_cells_grid(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t id,
                           const int32_t b[4], const int32_t g[MOY_UI_CELLS_G], const uint8_t *cells,
                           size_t cells_n, int n, int32_t cur, int32_t out[5]);
// A card of the cells (box `t`, under `clip`): where `focus`, the theme's focus mark round it,
// flat; then its title under it (`title`, at g's TITLE_DY, cut to TITLE_W) in the ui face,
// bold where `focus`, in `ink` over a black shadow where it names one (an override's colour,
// MOY_UI_O_NONE the theme's ink). The column look's title: in `ink` over a black shadow at
// 80%, else in the look's label ink over its label shadow (`label.ink`, `label.shadow`).
// The column look's tile (moy_ui_api_cells_plate): a desk icon's tile (moy_ui_bar_tile) at box
// `t` under `clip`, filled with `fill` (an override's colour, MOY_UI_O_NONE the tile's own).
void moy_ui_api_cells_plate(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const int32_t t[4],
                            const int32_t clip[4], int32_t fill);
void moy_ui_api_cells_card(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const int32_t g[MOY_UI_CELLS_G],
                           const int32_t t[4], const int32_t clip[4], int focus, moy_ui_span_t title,
                           int32_t ink);
// The cells' foot: on the handheld shelf, where `fade`, its last rows dissolving into the
// ground; the icons' caption band along the band's foot under a hairline,
// the current card's `title` in the title face from the first column's left and `sub`'s
// items (apart by tabs) after it in the dim ink, a dot between each two.
void moy_ui_api_cells_foot(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const int32_t g[MOY_UI_CELLS_G],
                           const int32_t b[4], const int32_t clip[4], int fade, moy_ui_span_t title,
                           moy_ui_span_t sub);
// The carousel look on the desk class (the desk home): laid out in content rect `b` (x, y, w,
// h, down to its hint strip) at font scale `fs`, `u` glass pixels a pixel, the hero at its top
// left, the details pane beside it (or under it where the pane beside would be narrower than
// 280 px), the shelf under them bleeding off the right edge, its caption over it. The hero is
// the largest whole multiple of the cover's side a quarter of the width holds with the shelf
// under it, else half the cover's side, and a shelf card is half the hero; the pane is as tall
// as the hero, or as its type needs (the title at TS, a line each at MS, KS and VS, a button
// BH tall and the rows of buttons under the first, BROWS px) where that is more. BROWS is the
// room the widest of `sets` wraps to in the pane, so the shelf stays put as the selection
// moves: each button as wide as its label in the print font at `fs` and its inset (a primary
// 148 px at the least, another 112, none wider than the pane), left to right 14 px apart, a
// danger three gaps apart, one that does not fit starting the next row; where a set wraps,
// every button the widest one's width, and a danger starting a row a row's gap (8 px) lower.
// A pane narrowed by a smaller hero is laid out again, three times at the most. A short band
// drops the pane's facts, then its metadata (FACTS, META 0), and halves the hero down to an
// eighth of the cover. The shelf's caption stands 42 px under the details and what height is
// left goes under the shelf; with no `keys` (touch: no hint strip) the shelf keeps at most
// its margin under it. out[MOY_UI_DESK_*]: the hero's box, the pane's (x, y, w, h), the
// shelf's band (its caption, its cards, their lift and their shadows), a shelf card's side,
// the shelf's top, its margin, the pane's type scales, the button height, the rows shown, the
// focus mark's reach, the shelf's gap and BROWS.
enum { MOY_UI_DESK_HERO = 0, MOY_UI_DESK_PANE = 4, MOY_UI_DESK_BAND = 8, MOY_UI_DESK_SIDE = 12,
       MOY_UI_DESK_SHELF_Y, MOY_UI_DESK_PAD, MOY_UI_DESK_TS, MOY_UI_DESK_MS, MOY_UI_DESK_KS,
       MOY_UI_DESK_VS, MOY_UI_DESK_BH, MOY_UI_DESK_FACTS, MOY_UI_DESK_META, MOY_UI_DESK_RING,
       MOY_UI_DESK_GAP, MOY_UI_DESK_BROWS, MOY_UI_DESK_G };
// The desk pane's button sets (moy_ui_api_carousel_desk's `sets`): `n` sets, set k `count[k]`
// buttons, each its label and its kind (an index of moy_ui_button_kinds).
enum { MOY_UI_DESK_SETS = 4, MOY_UI_DESK_SET_MAX = 4 };
typedef struct {
    int n;
    uint8_t count[MOY_UI_DESK_SETS];
    uint8_t kind[MOY_UI_DESK_SETS][MOY_UI_DESK_SET_MAX];
    moy_ui_span_t label[MOY_UI_DESK_SETS][MOY_UI_DESK_SET_MAX];
} moy_ui_desk_sets_t;
void moy_ui_api_carousel_desk(int fs, int u, int keys, const moy_ui_desk_sets_t *sets, const int32_t b[4],
                              int32_t out[MOY_UI_DESK_G]);
// The desk carousel's shelf in its band `b` (moy_ui_api_carousel_desk's band), its cards
// `side` px: one row of them its margin in, 20 px apart, under its caption (TITLE_DY the
// caption's scale), as cells geometry (MOY_UI_LOOK_DESK) the cells' extent, tile and hit
// answer for.
void moy_ui_api_desk_shelf_geom(int fs, int u, const int32_t b[4], int side, int32_t out[MOY_UI_CELLS_G]);
// The shelf card that holds (x, y), a card scrolled across its margin cut there; -1 none.
int moy_ui_api_desk_at(const int32_t g[MOY_UI_CELLS_G], const int32_t b[4], int32_t off, int n, int x,
                       int y);
// The shelf's caption over its first card, inside `clip`: `label` and the count `n`, apart by
// a dot, in the dim ink at the caption's scale.
void moy_ui_api_desk_caption(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const int32_t g[MOY_UI_CELLS_G],
                             const int32_t b[4], const int32_t clip[4], moy_ui_span_t label, int n);
// The largest side at most `limit` that shows a whole 128 px cover at a clean scale: a whole
// multiple of it, else its half, quarter or eighth.
int moy_ui_api_clean_side(int limit);
// A carousel tile's shadow: box `t` (x, y, w, h) under clip `clip` (what of its part shows,
// moy_ui_api_table_part's), the theme's card shadow, the smaller one off the `centre`.
void moy_ui_api_tile_cast(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const int32_t t[4],
                          const int32_t clip[4], int centre);
// A carousel tile in a row whose tiles rest at `card` px (-`card` on the desk's): where `mark`,
// its focus mark, the selected card's current mark where it is 2 (its box first shrunk by as
// much as the theme's mark grows a card, so a lifted card keeps its side, raised). out[0..3] the box its picture takes, out[4] that box's corner radius (the
// depth's card radius on a tile larger than `card`, 7/10 of it on the others; on the desk's
// that radius on a tile `-card` across, 7/5 of it on a larger one), out[5..8] the mark's box
// and out[9] the mark it drew (1 the focus mark, 2 the current one, 0 none):
// moy_ui_api_tile_end's.
void moy_ui_api_tile(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const int32_t t[4],
                     const int32_t clip[4], int card, int mark, int32_t out[10]);
// The corner radius of a carousel tile `side` px across in a row whose tiles rest at `card`
// px (moy_ui_api_tile's out[4] for a tile that wears no mark): the depth's card radius on
// a tile larger than `card`, 7/10 of it on the others.
int moy_ui_api_tile_radius(int side, int card);
// A tile with no picture of its own: icon `icon` on a tinted tile in its picture's box
// (moy_ui_card_blank; empty: the tile alone).
void moy_ui_api_tile_blank(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const int32_t tile[10],
                           const int32_t clip[4], moy_ui_span_t icon);
// After the picture: the lifted tile's rim, where moy_ui_api_tile drew a mark.
void moy_ui_api_tile_end(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const int32_t tile[10],
                         const int32_t clip[4]);
// The caption under a carousel's tiles (geometry `g`, moy_ui_api_carousel_geom's, band
// `band`), drawn inside `clip`: `title` in the hero face at its scale, cut to the band less
// 8 px a side at the font scale and centred; `sub`'s items (apart by tabs) in the ui face, centred, a dot
// between each two. In the theme's ink and dim ink, or both in `ink` (an override's colour:
// RGB or MOY_UI_O_ROLE + a token; MOY_UI_O_NONE the theme's), then each over a black shadow
// a pixel right and down.
void moy_ui_api_carousel_caption(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const int32_t band[4],
                                 const int32_t clip[4], const int32_t g[10], moy_ui_span_t title,
                                 moy_ui_span_t sub, int32_t ink);
// The table drawn last, where it keeps its parts (o->keep): the next rect
// of its view the frame draws (its floor) into out[0..3], 1, for an app
// that puts its own ground back there before its parts draw; the parts
// moy_ui_api_table_part answers are then those that meet it, each clipped
// to the floor rect it meets. After the last: 0 where every buffer the
// canvas presents holds the table as this frame draws it, -1 where one
// lags (the frame owes the next), -2 where they hold it but for what was
// drawn over it (o->over_*), which no frame of the table's brings back. A frame whose buffer holds the table's
// paint under its key at its scroll draws the rows whose cells, gen or
// marks changed since and what was drawn over that paint (o->over_*); any
// other frame draws the view whole. A table that keeps nothing answers
// its view, then 0.
int32_t moy_ui_api_table_floor(moy_ui_ctx_t *c, int32_t out[4]);
// Before moy_ui_api_table_floor: the next rect of the floor the buffer the
// last frame painted holds as this frame draws it -- every part that meets
// it unchanged since that paint (its cells, gen and marks; nothing drawn
// over it), that paint the app's alone, its table's key and scroll this
// frame's -- into out[0..3], 1, for the app to copy out of that buffer
// (the canvas's copy_last): the floor and the parts then pass it by. 0
// after the last. `back` gives the rect answered last back to the floor
// (a canvas that could not copy it), answering 0.
int32_t moy_ui_api_table_copy(moy_ui_ctx_t *c, int32_t out[4], int back);
// The move of the kept table's view this frame makes out of the buffer the
// last frame painted (o->shift; the buffer this frame paints lacks the
// table at its scroll, the frame before this one painted it kept under
// this key and geometry, at its own): the view into out[0..3] and the
// move along its axis into out[4] (px, 0 where the scroll is the same:
// the view copied), 1, for the app to make it (the canvas's shift_last,
// then its fence) before the floor draws -- the band the move uncovers,
// the parts that changed since that paint, what was drawn over it and
// the fade; else 0. With `back` (the canvas could not move it) the floor
// is the view whole, 0.
int32_t moy_ui_api_table_shift(moy_ui_ctx_t *c, int32_t out[5], int back);
// Whether the buffer this frame paints holds part `id` of the app's page
// as a frame drew it under `key`: the buffers RETAINED_FRAMES back, the
// frames between this context's paints, that paint the app's alone and
// `held` named there with `key`. Names it under `key` for this frame's
// paint, which the app draws where it answers 0.
int moy_ui_api_held(moy_ui_ctx_t *c, moy_ui_span_t id, int32_t key);
// Whether the buffer the last frame painted holds part `id` as that frame
// named it under `key` (moy_ui_api_held): the frame before this one, this
// context's paint and the app's alone; for a part the app copies out of
// that buffer. Names nothing.
int moy_ui_api_held_last(const moy_ui_ctx_t *c, moy_ui_span_t id, int32_t key);
// Whether every buffer the canvas presents holds every part this frame
// named (moy_ui_api_held) as it names it: the paints before this one, a
// buffer each, this context's, one a frame, each naming each part under
// the same key -- with no kept table drawn too. 0 where nothing is kept.
int moy_ui_api_held_all(const moy_ui_ctx_t *c);
// The faces of a table's parts kept drawn: each part drawn once into a
// square slot of a layer the app owns, then stamped from it. The engine
// keeps the slots' record -- which part's face each holds, which was
// stamped least recently -- and the app draws: a face into the slot the
// engine names, the slot onto its canvas. It keeps one such record, held
// by the context that asked last (another's asking forgets its faces), in
// that context (moy_ui_faces_t; MOY_UI_FACE_SLOTS slots at most).
#define MOY_UI_SLOT_MINT 0x10000    // moy_ui_api_slot: draw the face into the slot first
// The table drawn last keeps its parts' faces in `cap` slots (at most
// MOY_UI_FACE_SLOTS; 0 keeps none), each a function of `key` -- what
// every face is drawn under beside its part's own content: the look, the
// slot's size, the layer -- and of its part: another key or cap forgets
// every face. Its parts are the order moy_ui_api_slot_next answers from.
// Answers the slots kept.
int32_t moy_ui_api_slots(moy_ui_ctx_t *c, int32_t cap, int32_t key);
// The face of a part drawn from what `name` and `gen` name (its content,
// hashed, and a generation of it the name does not carry: its picture's):
// the slot holding it, to stamp; else with `mint` the slot to draw it
// into, the one stamped least recently, | MOY_UI_SLOT_MINT; else -1, the
// part drawn as it is.
int32_t moy_ui_api_slot(moy_ui_ctx_t *c, moy_ui_span_t name, int32_t gen, int mint);
// The next part whose face a frame nothing waits on draws (its name and
// gen handed to moy_ui_api_slot with mint): the parts of the rows the table drawn
// last showed, then those of the row past its end, then those of the row
// before its start, nearest first -- no more of them than the slots kept,
// so a round's minting never takes the slot of a part it named; -1 after
// the last, and the order starts again (as moy_ui_api_slots starts it).
int32_t moy_ui_api_slot_next(moy_ui_ctx_t *c);

// -- blocks of fields an app sets through the engine (moy_ui_api_block_*) ------
// A block is MOY_UI_BLOCK_FIELDS fields the state a part shows lies in (a
// bar's: its clock text, its zone's generation, the item the keys are on),
// each set through the engine as it changes, so a change is known as it
// is made: the block's generation moves with every change (one count
// across the blocks), moy_ui_api_block_since answers the fields set to
// another value after a generation (what a strip drawn at it draws again;
// every field of a block the engine does not hold), and its key is what
// every field shows, hashed (a key that matches again once every field is
// back). MOY_UI_BLOCKS blocks, by id, in memory taken at the first set
// (PSRAM on a board; a set that cannot have it answers a change, and the
// block reads as not held); one more takes the one set longest
// ago, whose fields are then set past any generation a part kept.
#define MOY_UI_BLOCKS 16
#define MOY_UI_BLOCK_FIELDS 32
// An instance's blocks (NULL: the main instance's).
int moy_ui_api_block_set(moy_ui_inst_t *I, moy_ui_span_t id, int field,
                         uint32_t value);                          // 1 where it changed
int32_t moy_ui_api_block_gen(moy_ui_inst_t *I, moy_ui_span_t id);  // its generation (0: not held)
uint32_t moy_ui_api_block_since(moy_ui_inst_t *I, moy_ui_span_t id,
                                int32_t gen);                      // the fields set after `gen`
int32_t moy_ui_api_block_key(moy_ui_inst_t *I,
                             moy_ui_span_t id);  // what its fields show, hashed (30 bits)
// The page's end, after its rows: where they run on below what shows, a
// fade at the foot of the page, over the hint band's top edge where the
// page has one; and over everything, the tooltip of a tool a resting
// pointer is over (ui.tool, moy_ui_api_tip). Inside a nested page it
// closes that page's parts alone.
void moy_ui_api_end(moy_ui_ctx_t *c, const moy_ui_sink_t *s);
// The page is done, its fades left to ui.end: what it drew is kept for the
// next frame's plan, as ui.end and the next page keep it, and the tooltip a
// resting pointer earned is drawn over it, as ui.end draws it.
void moy_ui_api_page_done(moy_ui_ctx_t *c, const moy_ui_sink_t *s);
// The top page done (moy_ui_api_page_done) drew what the next frame's begin would change: it
// closed short of its scroll (its rows end above what it showed: rows hidden, a glide past
// them), or focus is on a stop of it the last frame drew and this pass drew none of (where no
// dialog drew). Answers 1 with its scroll clamped, the focus passed to the nearest stop the
// pass drew, and the frame ready for the page's pass to run again from moy_ui_api_page: its
// stops back to the page's, the input the first pass took gone (no stop takes it twice), the
// shift floor off (the second pass draws the page whole, and the frame is told the host as a
// whole one). 0, and nothing changed, otherwise.
int moy_ui_api_page_again(moy_ui_ctx_t *c);
// A tool (§1): an icon button in ui.at's rect (else a row of the page),
// flat but for its marks: the current mark where o->current, the focus mark
// by its size, at half strength where o->disabled. `label` is its word,
// its text after a tab the key it answers to: on the handheld the word
// stands under the icon; on the desk it is the tooltip, with the key, that a
// resting pointer shows under the tool (drawn at ui.end). Answers true the
// frame it is activated.
int moy_ui_api_tool(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t icon,
                    moy_ui_span_t label, const moy_ui_over_t *o);
// The stop drawn last, where it is the stop of o's id, wears `label` as a
// tool's tooltip (drawn at ui.end) while a resting pointer is over it on the
// desk: a button drawn as its icon alone keeps its word this way.
void moy_ui_api_tip(moy_ui_ctx_t *c, const moy_ui_over_t *o, moy_ui_span_t label);
// An empty status band filling box b: drawn through the pass's floor, as a
// row's cells are, where a direct moy_ui_status would paint over the pixels a
// rows frame keeps.
void moy_ui_api_status_band(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_box_t b);
// A rule (§1): a line in the structure colour, one pixel at the scale
// across ui.at's rect (down it where the rect is taller than wide), else a
// row of the page's with the line across its middle.
void moy_ui_api_rule(moy_ui_ctx_t *c, const moy_ui_sink_t *s);
// The title of the top page the frame drawn last opened (ui.page's), "" for
// none: what the host's bar and a desk window's title name the page by.
const char *moy_ui_api_page_title(const moy_ui_ctx_t *c);
// The host's back (the bar's chevron, a window's, Esc, B and the T-Deck's
// K) over the frame drawn last: 1 where the app takes it -- a field's edit
// is cancelled or a popover it drew dismissed (moy_ui_api_cancel), else the
// frame's way back is taken (moy_ui_api_way) -- and 0 where it has no view
// to step out of, so the host leaves the app. `take` 0 only asks.
int moy_ui_api_back(moy_ui_ctx_t *c, int take);
// This frame's page has a way back (`on`: a page under it, a dialog, a
// popover, a back role) that its front takes when the host's back comes
// (the UI tree engine's, for a front that asks it: UIT_F_BACK). A frame's
// begin clears it.
void moy_ui_api_way(moy_ui_ctx_t *c, int on);
// Whether the host took the way back since this was asked last
// (moy_ui_api_back with `take`): 1 once, then 0.
int moy_ui_api_way_taken(moy_ui_ctx_t *c);
// The host's cancel (the T-Deck's Mic, and the back above) over the frame
// drawn last: 1 where the focused field's edit is open (moy_ui_api_edit_cancel)
// and then, with `take`, the next pass ends it, giving the field back the
// text it began from (or Enter last left it; the app's ui.field answers it),
// focus staying on the field; else 1 where a popover is open, which the
// next frame dismisses (ui.popover answers false); 0 where neither is, so
// the key keeps its own meaning.
int moy_ui_api_cancel(moy_ui_ctx_t *c, int take);
// moy_ui_api_cancel's field half: 1 where the focused field's edit is open,
// but an edit="open" field's with nothing to give back (its page's Back
// then goes on: the dialog, the popover, the strip it types in closes).
int moy_ui_api_edit_cancel(moy_ui_ctx_t *c, int take);
// Whether the frame drawn last owes the next though no input comes: a
// dialog or a popover laid out from a stale measure, or a reveal its pass
// set (a list's or a table's row stepped where begin could not reveal it, a
// focus moved by the app).
int moy_ui_api_owes(const moy_ui_ctx_t *c);
// Whether this frame's begin moved the focus or a page's scroll.
int moy_ui_api_moved(const moy_ui_ctx_t *c);
// Whether a page of the context moves on its own -- a fling coasts or a
// glide eases -- so the next frame is due though no input comes: the
// declared animation (docs/surface_model_v1.md §3's Class B) a host's frame
// gate reads.
int moy_ui_api_moving(const moy_ui_ctx_t *c);
// The scroll of the page that lies under (x, y) as the frame drawn last laid
// it out -- the offset a drag at that point moves, in pixels -- or -1 where
// no page lies there. A measuring tool's probe (tools/input_bench.py).
int32_t moy_ui_api_offset(moy_ui_ctx_t *c, int x, int y);
// The fades drawn at the edges lists run on past (a page's foot, a scroll
// region's, a cut popover body's, a table's), in every context of instance
// I (NULL: the main one) since the count was last reset; `reset` zeroes it
// after reading. The review kit's net that a list with hidden rows says so.
uint32_t moy_ui_api_fades(moy_ui_inst_t *I, int reset);
// The frames owed because a widget had no size kept to show at (a popover's
// first frame where the canvas cannot lend it the room to draw at once:
// laid out, drawn the next), likewise.
uint32_t moy_ui_api_owed(moy_ui_inst_t *I, int reset);
// Whether a frame began in a context of instance I (NULL: the main one)
// since the bits were last reset (MOY_UI_DIMS_BEGUN), and whether one drew
// what dims its whole surface under it to its foot, no hint band left lit
// there (MOY_UI_DIMS_DIMMED): a dialog, a menu that washes (`wash` 1) or
// ui.wash; `reset` zeroes them after reading. A window's frame dims its
// body under the surface with it (WindowChrome._win_chrome).
#define MOY_UI_DIMS_BEGUN 1
#define MOY_UI_DIMS_DIMMED 2
uint32_t moy_ui_api_dims(moy_ui_inst_t *I, int reset);
// out: x, y, w, h, state.
void moy_ui_api_part(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t id, int w, int h,
                     const moy_ui_over_t *o, int32_t out[5]);
// ui.part_at(): where the pointer is inside the part answered last this
// frame, from its top-left: where the tap that activated it was released
// (its state ACTIVATED by the pointer), else where the pointer is while it
// presses or hovers the part (a press held on a part with no page under
// it, or with nav off, stays its own through a drag). 1 with x, y at out;
// 0 otherwise (the part activated by a key, the pointer off it, no part
// this frame).
int moy_ui_api_part_at(const moy_ui_ctx_t *c, int32_t out[2]);
// ui.measure(): the box the next call of verb `kind` with `text` and `o`
// would take where it is called, drawing nothing and placing nothing:
// x, y, w, h and the stack's step at out (y where the stack stands, or
// ui.at's; the step how far the stack moves down past it, 0 under ui.at).
// MOY_UI_MEASURE_LABEL: a label, its text options (moy_ui_api_text) taken
// as the label takes them; w its text's width, at most its row's.
// MOY_UI_MEASURE_BUTTON: a button, w its natural width (its label and a pad
// each side, a minimum, at most the row's), h its row's; where `o` carries
// `fit`, its focus ring's reach more each side but the foot.
// MOY_UI_MEASURE_PROGRESS: a progress row placed by ui.at, h the height it
// draws tall at (its label and percent on a line, its bar under them), w
// its row's.
// MOY_UI_MEASURE_LINK: a link row, `text` its label and its value joined by
// a tab; w the width that draws both whole (its pads, an icon before it, the
// chevron: moy_ui_vrow_w), at most the row's, h its row's.
// MOY_UI_MEASURE_SEG: a seg row (ui.choice's MOY_UI_V_SEG), `text` its label
// and its options (NUL-separated, as ui.choice takes them) joined by a tab;
// w and h as a link row's. 1, or 0 for an unknown kind.
enum { MOY_UI_MEASURE_LABEL = 0, MOY_UI_MEASURE_BUTTON = 1, MOY_UI_MEASURE_PROGRESS = 2,
       MOY_UI_MEASURE_LINK = 3, MOY_UI_MEASURE_SEG = 4 };
int moy_ui_api_measure(moy_ui_ctx_t *c, const moy_ui_sink_t *s, int kind, moy_ui_span_t text,
                       const moy_ui_over_t *o, int32_t out[5]);
// ui.space(h): the stack moves `h` pixels down (0 or less: none), as a row
// that draws nothing and is no stop would, with no gap after it (a column
// the caller centres from its measure).
void moy_ui_api_space(moy_ui_ctx_t *c, int h);
// ui.dock(h): the open page's last `h` pixels (at most its height) become a
// docked foot's: the page's room ends above them, as the keys band's does
// (moy_ui_api_hints with no `at`), on the ground the page drew; their box at
// out. 0 where no page is open.
int moy_ui_api_dock(moy_ui_ctx_t *c, int h, int32_t out[4]);
// ui.split(id, dir, sizes, o) (docs/history/ui_api_2026-10.md §5a): ui.at's
// rect (else the page's, from its row cursor down) cut into `n` panes along
// one axis, `gap` pixels apart -- left to right, or with MOY_UI_SPLIT_Y top
// to bottom -- pane i sizes[i] long, the last taking what is left. Writes
// each pane's x, y, w, h at out, then MOY_UI_SPLIT_OUT words: the divider
// held or let go this frame (-1 none), the position a drag takes its gap to
// (its x, or its y), the side it stopped at (-1 none, 0 the pane before it
// at its minimum, 1 the pane after) and MOY_UI_SPD_* bits.
//
// With MOY_UI_SPLIT_FOCUS the panes hold a focused pane, opt's CUR (-1
// none), which the split answers as it moves: to the pane a press goes down
// in, and, as focus moves between groups, to the pane the focused stop lies
// in on the frame the focus moves; else -1 is answered. A split with focus
// or a divider records its panes until the next pass, CUR marking the one
// the keys reach (moy_ui_api_split_frame, moy_ui_api_split_toward).
//
// With MOY_UI_SPLIT_DRAG each gap is a divider, kept by the split's id: a
// press on it (HIT_W across, HIT_L along, centred; 0 the gap's) holds it,
// a drag past SLOP pixels moves it, and its line (LINE across, in `value`)
// shows where; on the release the two sizes beside it are written back to
// `sizes`, neither under its minimum (`mins`, NULL none). Its handle is a
// pill HANDLE_W across and HANDLE_L along in `border` (0: the gap, and six
// gaps). A split with neither stays the rect algebra and draws nothing.
// Words of opt that are 0 take their defaults.
enum {
    MOY_UI_SPLIT_Y = 1, MOY_UI_SPLIT_FOCUS = 2, MOY_UI_SPLIT_DRAG = 4,
};
enum {
    MOY_UI_SPO_FLAGS = 0, MOY_UI_SPO_GAP, MOY_UI_SPO_CUR, MOY_UI_SPO_SLOP, MOY_UI_SPO_HIT_W,
    MOY_UI_SPO_HIT_L, MOY_UI_SPO_HANDLE_W, MOY_UI_SPO_HANDLE_L, MOY_UI_SPO_LINE,
    MOY_UI_SPO_N
};
enum { MOY_UI_SPD_LIVE = 1, MOY_UI_SPD_LET_GO = 2 };
#define MOY_UI_SPLIT_OUT 4
#define MOY_UI_SPLIT_MAX 16          // the panes a split cuts at most
int moy_ui_api_split(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t id, int32_t *sizes,
                     int n, const int32_t *mins, const int32_t *opt, int32_t *out);
// Whether (x, y) lies on a divider the last pass's splits drew, where a
// press would hold it.
int moy_ui_api_split_at(const moy_ui_ctx_t *c, int x, int y);
// The pointer's shape over (x, y) of the pass drawn last: MOY_UI_CURSOR_TEXT over a
// text field, MOY_UI_CURSOR_HAND over a stop a press marks (or a split's
// divider), else MOY_UI_CURSOR_ARROW.
enum { MOY_UI_CURSOR_ARROW = 0, MOY_UI_CURSOR_HAND = 1, MOY_UI_CURSOR_TEXT = 2 };
int moy_ui_api_cursor(const moy_ui_ctx_t *c, int x, int y);
// The split frame (docs/history/ui_api_2026-10.md §5a), asked before the frame
// begins: whether it draws the pane the keys reach alone. That pane is the
// one a split of the last pass named with its focus (opt's CUR), of the
// panes its splits cut (a pane a later split cut again is none). It is the
// frame's alone where the host has no input waiting for this context
// (`still`), the last pass drew no popover and held no divider, nothing is
// owed and no page moves, the WM says the target holds the page as the last
// frame left it (`known`), and `gen` -- what the context draws outside the
// pane is a function of, MOY_UI_SPLIT_WHOLE where it changes on its own --
// is the gen the last frame was asked with.
// `top`: the rows at the pane's top that the context's own pass draws (a
// header), which the pane's frame leaves. Answers MOY_UI_SF_ALONE with the
// pane's rect below `top` at out; MOY_UI_SF_LAGS with it where `lag` (x0,
// y0, x1, y1: what the target lags) reaches outside that rect, the frame
// drawing whole but changing that rect alone; MOY_UI_SF_WHOLE otherwise.
#define MOY_UI_SPLIT_WHOLE INT32_MIN
enum { MOY_UI_SF_WHOLE = 0, MOY_UI_SF_ALONE = 1, MOY_UI_SF_LAGS = 2 };
int moy_ui_api_split_frame(moy_ui_ctx_t *c, int32_t gen, int known, int still, int top,
                           const int32_t lag[4], int32_t out[4]);
// The pane of the last pass's splits that lies (dx, dy) from the one
// holding (x, y): of those whose centre lies that way, the nearest along
// it, a pane off to the side counting twice its distance across. 1 with
// its rect at out; 0 none (no pane holds (x, y), or none lies that way).
int moy_ui_api_split_toward(const moy_ui_ctx_t *c, int x, int y, int dx, int dy,
                            int32_t out[4]);
// Focus moved to `id` (id.p NULL: read only; a field over O2_TYPING it names
// begins its edit, though focus is on it already). The focused id's text into
// `buf` (NUL-terminated within `cap`); answers its length, -1 with none.
int moy_ui_api_focus(moy_ui_ctx_t *c, moy_ui_span_t id, char *buf, size_t cap);
// Focus moved to `id` ahead of the next frame, between frames (a host's):
// that frame's begin shows it, so it owes no frame of its own as a move
// inside a pass does.
void moy_ui_api_focus_ahead(moy_ui_ctx_t *c, moy_ui_span_t id);
int moy_ui_api_keys_taken(const moy_ui_ctx_t *c);
// Whether the stop holding focus in the frame drawn last is a field whose
// edit is open and the keys are this page's: the page is being typed into,
// so its surface takes the keyboard as text (a T-Deck's W A S D type there
// and step nothing).
int moy_ui_api_typing(const moy_ui_ctx_t *c);
// The same asked while a frame draws: a stop it has not drawn yet is read as
// the frame before drew it (what a band drawn before the field names).
int moy_ui_api_typing_drawing(const moy_ui_ctx_t *c);
// The keys another surface held when this frame began (MOY_UI_ELSEWHERE)
// came back mid-frame, before the pass drew its stops (a cart's editor handle
// let them go in its update): from here a stop takes the focus as on a frame
// begun with them, so the first frame after shows its mark.
void moy_ui_api_keys_back(moy_ui_ctx_t *c);
// The console's Paste fired (the desk's Ctrl+V): the field focused in this
// frame, begun already, takes `n` bytes of UTF-8 `text` at its caret, as many
// as its room holds, cut at a character boundary. A line break or a tab is a
// space and any other control byte is dropped. The console reads the text
// from its clipboard, so the app holds no clipboard grant; MOY_UI_API_PASTE
// bytes at most are kept.
void moy_ui_api_paste(moy_ui_ctx_t *c, const uint8_t *text, size_t n);
// Which way this frame's step found no stop past the focused one, outside a
// dialog (MOY_UI_EDGE_*, 0 none): the keys went past the page's top, foot,
// left or right, and focus stayed where it was.
enum { MOY_UI_EDGE_UP = 1, MOY_UI_EDGE_DOWN = 2, MOY_UI_EDGE_LEFT = 4, MOY_UI_EDGE_RIGHT = 8 };
int moy_ui_api_edge(const moy_ui_ctx_t *c);
// The keys enter the page travelling `dir` (MOY_UI_EDGE_*: the edge the page
// they left answered): the next begin, not elsewhere, lands focus on the stop
// nearest the side they come in by -- its first stop going down, its last
// going up, its rightmost going left, its leftmost going right -- of the
// stops the last frame drew, in the frame that draws it.
void moy_ui_api_enter(moy_ui_ctx_t *c, int dir);
// Whether the pointer is down on a stop its release may activate: a press
// that has not become a page's drag (nor caught a fling, which taps nothing).
int moy_ui_api_tap_armed(const moy_ui_ctx_t *c);
void moy_ui_api_at(moy_ui_ctx_t *c, int x, int y, int w, int h);
// While `on`, what a ui.at rect places draws clipped to the view the rows stack in now, as a
// stacked row's does: a flowing row's cells scroll with its page and end at its view. Answers
// whether it was on.
int moy_ui_api_cut(moy_ui_ctx_t *c, int on);
// The first draw of the page's (not a dialog's or a popover's) this frame that met the hints
// band, where it showed: 1 with its box at out, else 0. The UI checks' (tests/ui_checks.py).
int moy_ui_api_over_band(const moy_ui_ctx_t *c, int32_t out[4]);
// Where stop `id` drew in the frame drawn last (the host's: a popover beside
// a row, a test's tap), or the card of the popover `id` drawn then, or of
// the dialog titled `id`, or the button labelled `id` at that dialog's foot,
// or the view of the scroll region `id`: its box into out, 1; 0 where it
// drew no such stop, popover, dialog or region.
int moy_ui_api_box(const moy_ui_ctx_t *c, moy_ui_span_t id, int32_t out[4]);
// The part of stop `id`'s box the last frame drew that a press takes: its
// box inside its page's view (a dialog's inside its body; all of a
// popover's over a page), 0 wide where none of it shows; or the view of the scroll region
// or text view `id`. 1, or 0 where it drew no such stop or view.
int moy_ui_api_hit_box(const moy_ui_ctx_t *c, moy_ui_span_t id, int32_t out[4]);
// A duplicate id drawn this frame, its text, once per id (NULL none).
const char *moy_ui_api_dup(moy_ui_ctx_t *c);
// The stops the frame drew past the MOY_UI_API_STOPS it records (each drawn,
// and taking no focus or input), and from bit 16 the widgets that asked for
// kept state past the MOY_UI_API_KEEP ids it keeps (each drawn with none),
// once per answer that differs from the one told last; 0 otherwise.
int moy_ui_api_lost(moy_ui_ctx_t *c);

// What the pass drew over the app's own rows (a text view's overlay) into
// out (x, y, w, h; w 0: none): the popover's card, or the whole surface
// where ui.end drew a tooltip.
int moy_ui_api_pop_box(const moy_ui_ctx_t *c, int32_t out[4]);

// -- shift frames (docs/history/scroll_and_text_2026-10.md §3.3) ---------------------------
//
// A frame whose change is one region R's scroll plus rows the engine knows
// of draws R's rows only where they changed: its host moves the pixels the
// last frame drew in R by the scroll's move (a canvas's shift_last) and the
// pass draws the FLOOR -- the band the move exposed, the rows whose marks
// moved, the fades -- leaving the rest of R as moved. What licenses it is
// known at begin: the input the engine applied (a drag, a fling's or a
// glide's step, a focus move, a key typed into a field), the generation
// every page and picture inside R carries (`gen` in the override block), and
// the last pass having drawn R whole with nothing over it. A page with no
// gen, a stop placed by ui.at inside R, a part with no gen, a dialog, a
// popover, a press, an activation, a stepped value, a hover, a tooltip: the
// frame draws whole. The floor only widens during the pass: a stop that
// differs from the last frame's draws from its top to R's foot (but for one
// ui.at placed both frames that moved where the floor holds both its
// boxes, which moves nothing else), a picture
// whose gen moved, or a card's with none, draws its own box, a stop gone from R's tail leaves the
// ground. What a stop outside R draws into it (a box reaching in, a mark's
// reach) is floor where R moved or its marks changed, and where such a stop
// draws before R opens the floor is the pass's from its start.
enum { MOY_UI_SHIFT_NONE = 0, MOY_UI_SHIFT_MOVE = 1, MOY_UI_SHIFT_ROWS = 2 };
#define MOY_UI_SHIFT_WIDE 8         // moy_ui_api_shift_drawn: the floor took R from a stop down
// What a page holds, for its next frame's plan (moy_ui_keep_t's kd).
enum {
    MOY_UI_KD_DRAWN = 1,            // a page whose pass drew it
    MOY_UI_KD_GEN = 2,              // ...under a generation
    MOY_UI_KD_BAD = 4,              // ...holding what no shift may move (MOY_UI_SHIFT_NONE)
    MOY_UI_KD_PAGE = 8,             // a page (or a placed table's rows): its `a` is a scroll
    MOY_UI_KD_TABLE = 16,           // ...a placed table's rows, R its view
    MOY_UI_KD_AT = 32,              // ...holding a stop ui.at placed, which no move carries
    MOY_UI_KD_X = 64,               // ...a table whose rows lie side by side: `a` scrolls across
    MOY_UI_KD_HELD = 128,           // ...a page drawn under the gen the last frame drew it under, still
};
// After begin: the frame the engine licenses (MOY_UI_SHIFT_*). out: R's x,
// y, w, h on screen as the last frame drew it, dy, the shift that brings
// that frame's pixels to this one's scroll (0 on a rows frame), the rows of
// R its floor will draw as begin can know them (the floor only widens), the
// rows of R's pictures the floor leaves undrawn (summed per picture), and 0
// for a page, else a dialog's rows frame: the frames its card has stood as it
// is (at most 255). A dialog over a held page (`wash` false) whose app gives
// it a gen draws its rows alone on a frame whose input only typed into its
// field or moved its focus: R is its card and the drop under it as the last
// frame drew them, the floor the rows that input changed, and nothing outside
// R is the dialog's to draw -- the page under it is the host's, which puts it
// back on any other frame. A dialog that comes up otherwise than planned (its
// card, title, buttons, `wash` or gen) draws nothing that frame and owes the
// next.
int moy_ui_api_shift_plan(const moy_ui_ctx_t *c, int32_t out[8]);
// The host moved R's pixels (or the frame is a rows frame, whose R holds the
// last frame's as they are): this frame's pass draws R's floor alone.
void moy_ui_api_shift_arm(moy_ui_ctx_t *c);
// What the pass begun last drew (MOY_UI_SHIFT_*: NONE a whole frame, with
// MOY_UI_SHIFT_WIDE where a stop unlike the last frame's widened the floor
// to R's foot), and into *clean whether it left R's pixels the page's alone
// (nothing drawn over it: a tooltip, a toast, a dialog, a popover).
int moy_ui_api_shift_drawn(const moy_ui_ctx_t *c, int *clean);
// The floor's rects as the pass has them, x, y, w, h each, `cap` at most:
// their count, -1 where the pass draws whole (a test's probe).
int moy_ui_api_floor(const moy_ui_ctx_t *c, int32_t *out, int cap);
// The floor's bounding rect as the pass drew it, x, y, w, h on screen into
// out: 1, or 0 where the pass drew whole (or drew no floor at all).
int moy_ui_api_floor_box(const moy_ui_ctx_t *c, int32_t out[4]);
// What the pass's shift or rows frame changed of its canvas -- its floor,
// and the region it moved and the view moved inside it -- as x0, y0, x1, y1
// into out[0..3] (all 0 where nothing), and the rect it changed nothing
// else inside, x0, y0, x1, y1 into out[4..7]: R, which it draws through
// the floor alone, or the page holding R where that page drew under the
// gen it drew under the last frame, still and with no picture of no gen
// (what it draws outside R draws as it did; a dialog's rows frame's: the
// surface). 1, or 0 where the pass drew whole.
int moy_ui_api_change_box(const moy_ui_ctx_t *c, int32_t out[8]);
// A host's lag history (docs/history/scroll_and_text_2026-10.md §3.4): `slots`
// slots of 2 + 2 * `bands` words, a frame's in slot f % slots -- the frame,
// its kind (0 whole, 1 rows, 2 shift) and its floor's rows as `bands` pairs
// y0, y1 in order (an empty pair, 0 0, unused; past `bands`, the nearest
// merge). lag_note writes frame f's slot from the pass begun last.
void moy_ui_api_lag_note(const moy_ui_ctx_t *c, int32_t *hist, int slots, int bands,
                         int f, int kind);
// Whether the buffer frame f paints lags the frame before's page only in the
// rows the rows frames since f - n drew: their bands into out (`cap` pairs at
// most, merged as lag_note merges), their count (0, none), else -1.
int moy_ui_api_lag(const int32_t *hist, int slots, int bands, int f, int n,
                   int32_t *out, int cap);
// An app host's frame begins (runtime/toolkit/ui_draw.py's AppHost.begin): the
// frame begun last is noted as its pass left it, the frame begins as
// moy_ui_api_begin's, and the shift frame it may be is planned against the
// host's ring -- the canvas's part of it (moving pixels, the fence) is left
// to the host, which then arms it (moy_ui_api_host_arm). `in`, `surface`,
// `flags` and `fs` are moy_ui_api_begin's; `in`'s press words (buttons
// pressed, the key, the wheel) are cleared after, as a frame takes each
// once. Where the last pass drew a duplicate id, nothing begins: the answer
// is MOY_UI_HB_DUP, and the host logs it (moy_ui_api_dup) and begins again.
// `pf` is the console's frame (MOY_UI_PF_*), `hp` the host's words
// (MOY_UI_HP_*): its canvas, its tap, and the answers. Answers
// MOY_UI_HB_* bits.
enum {
    MOY_UI_PF_FRAME = 0,            // the painted frame's number
    MOY_UI_PF_ALONE,                // its content alone on the glass
    MOY_UI_PF_OVER,                 // ...but for what the console names it drew over it after
    MOY_UI_PF_WIN,                  // the windowed WM's word (ui_draw.window_frame)
    MOY_UI_PF_OVER_X, MOY_UI_PF_OVER_Y, MOY_UI_PF_OVER_W, MOY_UI_PF_OVER_H,
    MOY_UI_PF_OVER_F,               // ...that rect, and the frame it was drawn over
    MOY_UI_PF_KEY,                  // the paints' key: the look's epoch and the focus marks
    MOY_UI_PF_DT,                   // the loop's tick, which a begun frame's input takes
    MOY_UI_PF_LEN
};
enum {
    MOY_UI_HP_PLAN = 0,             // 8 words: the plan (moy_ui_api_shift_plan's)
    MOY_UI_HP_RETAINED = 8,         // the canvas's RETAINED_FRAMES (0 none)
    MOY_UI_HP_COST,                 // its SHIFT_COST, per mille of a row's raster (-1 none)
    MOY_UI_HP_OX, MOY_UI_HP_OY,     // its origin on the buffer
    MOY_UI_HP_SAME,                 // 1 the canvas, 2 the theme, of the frame begun last
    MOY_UI_HP_TAP,                  // the pointer's tap (a press, held or released: nonzero)
    MOY_UI_HP_HOST,                 // MOY_UI_HH_*: the host's own
    MOY_UI_HP_DEAD,                 // out: the directions whose steps moved nothing
    MOY_UI_HP_N,                    // out: the moves the canvas makes, then each x, y, w, h, dy
    MOY_UI_HP_MOVES,
    MOY_UI_HP_LEN = MOY_UI_HP_MOVES + 5 * MOY_UI_HOST_HIST * MOY_UI_HOST_BANDS
};
enum {
    MOY_UI_HH_HELD = 2,             // a dialog's rows frame is the host's to allow
};
enum {
    MOY_UI_HB_SETTLED = 1,          // moy_ui_api_begin's answer
    MOY_UI_HB_MOVING = 2,           // a page flings or glides
    MOY_UI_HB_EDGE = 4,             // an up press went past the page's top
    MOY_UI_HB_DUP = 8,              // nothing begun: a duplicate id the last pass drew waits to be logged
    MOY_UI_HB_SHIFT = 16,           // a shift frame: make hp's moves, then arm it
    MOY_UI_HB_HELD = 32,            // ...where the host's dialog allows the plan
    MOY_UI_HB_FENCE = 64,           // ...fencing them before the floor draws
};
int moy_ui_api_host_begin(moy_ui_ctx_t *c, int32_t *in, moy_ui_box_t surface, int flags,
                          int fs, const int32_t *pf, int32_t *hp);
// The host made every move its begin planned: this frame draws the floor
// alone. Answers the frame's dy (0, a rows frame).
int moy_ui_api_host_arm(moy_ui_ctx_t *c);
// The frame begun next draws whole (AppHost.whole, AppHost.again).
void moy_ui_api_host_whole(moy_ui_ctx_t *c);
// The frame begun last draws none of its page (its buffers hold it as the
// last frame drew it): where no pass of the frame draws it after all, the
// stops, the captions and the kept state the frame before left stand into
// the next frame, as though this one had drawn them.
void moy_ui_api_host_stand(moy_ui_ctx_t *c);
// The frame draws whole from here: a host saw an op that ignores the floor
// (a cart's cls) land on its page. The pass after it draws every stop.
void moy_ui_api_shift_break(moy_ui_ctx_t *c);
// ui.card_clip(rect): `r` (x, y, w, h, in and out) cut to the floor's rect
// the picture the last card or part answered lies in, which is where the
// app draws it on a shift frame; 0, `r` as it was, where the frame draws
// whole. An app that gives a picture a gen clips its picture to it. After
// a placed table that was R, `r` is a picture on its rows: cut to the rect
// of the floor its row lies in (the floor is whole rows there), else to
// nothing.
int moy_ui_api_card_clip(const moy_ui_ctx_t *c, int32_t r[4]);
// ui.band(): the rows of the page being laid out that this frame draws, as
// x, y, w, h in the page's coordinates (y from its rows' top): the floor's
// bounding rect on a shift frame, else what shows of the page. 0 where no
// page is open.
int moy_ui_api_band(const moy_ui_ctx_t *c, int32_t out[4]);
// ui.view(): where the next stacked row of the open page, or of the scroll
// region open innermost, lies and what shows of it, for a list that lays
// out only the rows in view: out the row cursor (content coordinates), the
// page's or region's scroll, its view's height, its width and the font
// scale. 0 where the next row would not stack on the page or region itself
// (no page open, a dialog or popover open innermost, a grid, a table's
// part, ui.at's rect, a snapping band).
int moy_ui_api_view(const moy_ui_ctx_t *c, int32_t out[5]);
// ui.keep(id, h): a stop the app does not draw this frame (it lies outside
// the band), carried forward as the last frame drew it -- a card of the open
// grid, else a row `h` high -- so layout, focus and the shift frame's checks
// see it. Answers its state bits.
int moy_ui_api_keep(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t id, int h);
// The L8 record assertion's net (tests only): with `on` 1 each stop's record
// is kept, and a shift frame whose stops differ from the last frame's
// outside the floor, or that draws a stop outside R reaching into it with
// the part of R it reaches not the floor's, counts a failure; answers the failures since the last
// call and zeroes them (`on` -1 reads, leaving the switch as it is); per
// instance (NULL: the main one).
uint32_t moy_ui_api_audit(moy_ui_inst_t *I, int on);

// A palette's cells, a stop (§1): `count` of the MOY64 colours from `first`,
// `cols` to a row, each a `side` square less `gap`, centred in the row the
// page places them in (in a box ui.at placed, as tall as it holds their rows,
// at most `side`, the gap at most a quarter of it); `edge` draws the border round them. The colour `cur`
// wears the current mark, and while focus is on them the keys' cursor; the
// arrows move it a cell (up at the top row and down at the last go on to the
// next stop). Enter, or a tap on a cell (which moves `cur` there), sets
// `*picked`. The colour `clear` (-1 none) shows as clear (moy_ui_cells_draw).
// Answers the new `cur`.
int32_t moy_ui_api_cells(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t id, int first,
                         int count, int cols, int side, int gap, int32_t cur, int edge, int clear,
                         const moy_ui_over_t *o, int *picked);

#endif // MOY_UI_API_H
