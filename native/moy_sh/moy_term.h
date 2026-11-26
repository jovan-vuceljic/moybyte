// moy_term: the terminal's cell grid, the VT100 subset a line program and a
// full-screen text app write (docs/os_2026-11/system.md section 1, "The
// terminal emulation"). The screen face (moy_sh_screen.h) feeds it the
// shell's output; the console draws its lines through `ui.text_view`, which
// maps the SGR colours to the theme, so the grid holds no pixels.
//
// THE GRID is a ring of `lines` lines of `cols` cells: the screen is its last
// `rows`, the lines above it the scrollback, which a line scrolled off the
// screen's top joins and the oldest leaves when the ring is full. A cell is
// one word: the codepoint in its low 19 bits (one past U+7FFFF is U+FFFD:
// the planes above hold no character a console's font draws), the reverse
// bit, the ink above (MOY_TERM_FG_AT: 0-15 the ANSI colours, which a text
// view draws in the theme's tones, MOY_TERM_INK the default, MOY_TERM_PAL and
// up the console's sixteen base colours exactly), the dim bit, and the ground
// (MOY_TERM_BG_AT: 0 none, 1-16 a base colour). The
// ring's memory comes from the caller's `alloc` at moy_term_new and resize
// (PSRAM on a board), nothing else is kept.
//
// WHAT IT READS. Text as UTF-8 (a malformed sequence is U+FFFD); `\n` is a
// new line at column 0, as a tty's output processing makes it; `\r`, `\b`,
// `\t` (the next stop of eight); a write past the last column wraps at the
// next character. Escapes, `ESC [` with its parameters:
//   A B C D E F G d H f   the cursor up, down, right, left, to a line's start
//                         below or above, to a column, a row, a place
//   J (0 1 2 3)           erase below, above, the screen, the scrollback
//   K (0 1 2)             erase right, left, the line
//   m                     SGR: 0 reset, 2 dim, 22 normal, 7 reverse, 27 not,
//                         30-37 and 90-97 the ink, 39 the default, 38;5;N
//                         its first sixteen, 38;2;R;G;B the nearest base
//                         colour; 48;2;R;G;B and 48;5;N (N < 16: that base
//                         colour) the ground, 49 none; the rest (bold,
//                         40-47) are read and drop
//   s u, ESC 7 ESC 8      the cursor saved and restored
//   ? 25 h / l            the cursor shown and hidden
// and ESC D (index), ESC E (next line), ESC M (up a row), ESC c (reset).
// Anything else is read whole and ignored.
//
// THE VIEW. The lines a view shows are the scrollback and the screen down to
// its last row written or the cursor's, so a terminal that has printed three
// lines shows three, as a log does. Every held line has a number that never
// changes while it is held (`base` is the oldest's): moy_term_take answers
// which are held and the lowest that changed since the last take, so a face
// rebuilds those lines and no others.

#ifndef MOY_TERM_H
#define MOY_TERM_H

#include <stddef.h>
#include <stdint.h>

#define MOY_TERM_FG_AT 20
#define MOY_TERM_INK 16u                // the default ink
#define MOY_TERM_PAL 32u                // + i: base colour i, exactly
#define MOY_TERM_REV (1u << 19)
#define MOY_TERM_DIM (1u << 26)
#define MOY_TERM_BG_AT 27
#define MOY_TERM_CP_MAX 0x7FFFFu
#define MOY_TERM_CP(cell) ((cell) & MOY_TERM_CP_MAX)
#define MOY_TERM_FG(cell) (((cell) >> MOY_TERM_FG_AT) & 0x3Fu)
#define MOY_TERM_BG(cell) ((cell) >> MOY_TERM_BG_AT)

// The base colour nearest `rgb` (0xRRGGBB): its index, 0-15, among the
// console's palette's first sixteen (moy_theme_moy64); -1 in a build that
// links no palette, where a cell's base colour reaches the client as its own
// (38;5;N).
int moy_term_nearest(uint32_t rgb);

// The shell's colours are the palette's base colours, never an ANSI one's:
// base colour `base` (0-15) as an ink's or (`ground`) a ground's SGR, its RGB
// (38;2 / 48;2; 38;5;N in a build that links no palette), into `o`, which
// holds MOY_TERM_SGR_BYTES. The accent is what the shell marks with: the
// typed line, a text app's title and mode, top's selected row (vi's
// selection is reverse video): a reset, then its ink, into `o`
// (MOY_TERM_ACCENT_BYTES), which it returns.
#define MOY_TERM_SGR_BYTES 24u
#define MOY_TERM_ACCENT_BYTES (MOY_TERM_SGR_BYTES + 4u)
#define MOY_TERM_ACCENT 12              // the palette's blue
size_t moy_term_base_sgr(char *o, int ground, int base);
const char *moy_term_accent(char *o);

typedef struct moy_term moy_term_t;

typedef void *(*moy_term_alloc_fn)(void *ctx, size_t n);
typedef void (*moy_term_free_fn)(void *ctx, void *p);

// A grid of `rows` by `cols` with `lines` lines in all (at least `rows`); NULL
// when `alloc` refuses.
moy_term_t *moy_term_new(int cols, int rows, int lines, moy_term_alloc_fn alloc,
                         moy_term_free_fn free, void *ctx);
void moy_term_free(moy_term_t *t);

// Feed `n` bytes of output.
void moy_term_write(moy_term_t *t, const char *p, size_t n);

// A new size: every held line keeps its cells up to the new width (a
// terminal does not reflow), the cursor its line. -1 when `alloc` refuses,
// the grid as it was.
int moy_term_resize(moy_term_t *t, int cols, int rows);
void moy_term_size(const moy_term_t *t, int *cols, int *rows);

// Moves with every change, the cursor's included.
uint32_t moy_term_gen(const moy_term_t *t);

// out[0] the number of the oldest line held, out[1] how many lines the view
// shows, out[2] the lowest line number changed since the last take (out[0] +
// out[1] when none did).
void moy_term_take(moy_term_t *t, uint32_t out[3]);

// The view's line `i` (0 the oldest held) as UTF-8 with an SGR escape where
// its ink, its ground or its reverse changes, its trailing blanks dropped (a
// blank with a ground or reversed is kept), into `out` (NUL-terminated, cut
// at a character that does not fit): its bytes.
size_t moy_term_line(const moy_term_t *t, int i, char *out, size_t cap);

// The bytes a line's buffer holds a column, plus 8: a cell's ANSI ink and
// a UTF-8 character at most, with room for the RGB escapes of a line such as
// neofetch's logo; a line that changes colour more often is cut there.
#define MOY_TERM_COL_BYTES 12u

// The cursor: out[0] its view line, out[1] its column, out[2] 1 shown.
void moy_term_cursor(const moy_term_t *t, int out[3]);

#endif // MOY_TERM_H
