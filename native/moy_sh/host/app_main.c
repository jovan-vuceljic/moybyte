// The text apps' host harness, for the memory they take: a session over a
// folder whose host puts a text app in front (`edit`, `vi` and its names,
// `top`) on an app heap the harness meters, fed a script as the serial face
// feeds it -- a line to the shell while no app is in front, the app's keys in
// caret notation while one is (^X a control key, ^[ Esc, so ^[[A is up; ^?
// Delete; ^^ a caret) -- printing the app's last row after each line, and
// `end` when the app ends.
//
//   app_main ROOT SCRIPT          MOY_SH_APP_ALLOC_MAX: the largest request
//                                 the app heap grants the app's own code
//
// THE METER counts the app heap's requests from each open. A full-screen
// app's first four are moy_sh_app_new's (the front, the app's record, its
// screen's record and cells; a straight one's first two, as it keeps no
// screen); the rest are what the app asks for itself
// (an editor's text, a register, an undo, a save), and only those are
// capped: past the cap a request is refused, as a heap whose largest free
// block is that big refuses it. A `%meter` line prints, for the app's own
// requests since the open, the largest, the most held at once and what is
// held now; the store's largest request and the most it held
// (moy_store_host.c) since the open or the last `%meter`; and the sizes of
// the open's own four. `%size COLS ROWS` sizes the next app's screen (40 by
// 12 until then); `%straight` opens the next one straight (moy_sh_app.h), its
// writes into a screen of the harness's own as a terminal shows them, drawn
// whole after the open as a face draws it; `%screen` prints the screen.

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "moy_log.h"
#include "moy_sh.h"
#include "moy_sh_app.h"
#include "moy_term.h"

void moy_store_host_meter(long *largest, long *most, int reset);

#define FIXED 4                         // moy_sh_app_new's own requests, at most
#define HEAD 16                         // the size kept before each grant

static struct {
    size_t cap;                         // 0: none
    int count;                          // requests since the open
    int nfixed;                         // how many of the first are the open's own
    size_t largest, most, live, refused;
    size_t fixed[FIXED];                // the sizes of moy_sh_app_new's own
} M;

static moy_sh_app_t *app;
static moy_term_t *client;              // a straight app's terminal
static int cols = 40, rows = 12, straight;

static void *app_alloc(void *ctx, size_t n) {
    (void)ctx;
    int fixed = M.count < M.nfixed;
    if (fixed) {
        M.fixed[M.count] = n;
    }
    M.count++;
    if (!fixed && M.cap != 0 && n > M.cap) {
        M.refused++;
        return NULL;
    }
    unsigned char *p = malloc(n + HEAD);
    if (p == NULL) {
        return NULL;
    }
    memcpy(p, &n, sizeof n);
    p[sizeof n] = (unsigned char)fixed;
    if (!fixed) {
        M.live += n;
        M.most = M.live > M.most ? M.live : M.most;
        M.largest = n > M.largest ? n : M.largest;
    }
    return p + HEAD;
}

static void app_free(void *ctx, void *q) {
    (void)ctx;
    unsigned char *p = (unsigned char *)q - HEAD;
    size_t n;
    memcpy(&n, p, sizeof n);
    if (!p[sizeof n]) {
        M.live -= n;
    }
    free(p);
}

static void *h_alloc(void *ctx, size_t n) {
    (void)ctx;
    return malloc(n);
}

static void h_free(void *ctx, void *p) {
    (void)ctx;
    free(p);
}

static void h_out(void *ctx, int stream, const char *p, size_t n) {
    (void)ctx;
    (void)stream;
    fwrite(p, 1, n, stdout);
    fflush(stdout);
}

static void *t_alloc(void *ctx, size_t n) {
    (void)ctx;
    return malloc(n);
}

static void client_out(void *ctx, const char *p, size_t n) {
    (void)ctx;
    moy_term_write(client, p, n);
}

static int h_app(void *ctx, moy_sh_t *s, int argc, char **argv) {
    (void)ctx;
    if (app != NULL || moy_sh_app_find(argv[0]) == NULL) {
        return app != NULL ? 1 : MOY_SH_NOT_FOUND;
    }
    long l, m;
    moy_store_host_meter(&l, &m, 1);
    M.count = 0;
    M.nfixed = straight ? 2 : FIXED;
    memset(M.fixed, 0, sizeof M.fixed);
    M.largest = M.most = M.live = M.refused = 0;
    moy_sh_app_heap_t heap = { app_alloc, app_free, NULL };
    int status;
    moy_term_free(client);
    client = straight ? moy_term_new(cols, rows, rows, t_alloc, h_free, NULL) : NULL;
    app = moy_sh_app_new(s, &heap, cols, rows, 1, NULL, straight ? client_out : NULL, NULL,
                         argc, argv, &status);
    if (app != NULL && straight) {
        moy_sh_app_draw(app);
    }
    straight = 0;
    return status;
}

static moy_term_t *screen(void) {
    return app == NULL ? NULL : client != NULL ? client : moy_sh_app_term(app);
}

// Row `i` of the app's screen, its inks dropped.
static void show_row(int i) {
    char row[1024], out[1024];
    size_t n = moy_term_line(screen(), i, row, sizeof row), k = 0;
    for (size_t j = 0; j < n && k + 1 < sizeof out; j++) {
        if (row[j] == 0x1b) {
            while (j < n && row[j] != 'm') {
                j++;
            }
        } else {
            out[k++] = row[j];
        }
    }
    out[k] = 0;
    printf("| %s\n", out);
}

static void show_last(void) {
    if (screen() != NULL) {
        show_row(rows - 1);
    }
}

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: app_main ROOT SCRIPT\n");
        return 2;
    }
    const char *cap = getenv("MOY_SH_APP_ALLOC_MAX");
    M.cap = cap != NULL ? (size_t)strtoul(cap, NULL, 10) : 0;
    moy_log_init(4096);
    moy_sh_host_t host = {
        .alloc = h_alloc, .free = h_free, .out = h_out, .root = argv[1], .app = h_app,
    };
    moy_sh_t *s = moy_sh_new(&host, 64 * 1024, "/", "/");
    FILE *f = fopen(argv[2], "r");
    if (s == NULL || f == NULL) {
        fprintf(stderr, "app_main: no session or no script\n");
        return 2;
    }
    static char line[1 << 16], keys[1 << 16];
    while (fgets(line, sizeof line, f) != NULL) {
        size_t n = strcspn(line, "\n");
        line[n] = 0;
        if (strncmp(line, "%size ", 6) == 0) {
            sscanf(line + 6, "%d %d", &cols, &rows);
        } else if (strcmp(line, "%straight") == 0) {
            straight = 1;
        } else if (strcmp(line, "%screen") == 0) {
            for (int i = 0; app != NULL && i < rows; i++) {
                show_row(i);
            }
        } else if (strcmp(line, "%meter") == 0) {
            long sl, sm;
            moy_store_host_meter(&sl, &sm, 1);
            printf("meter largest %zu most %zu live %zu refused %zu store largest %ld most %ld"
                   " fixed %zu %zu %zu %zu\n", M.largest, M.most, M.live, M.refused, sl, sm,
                   M.fixed[0], M.fixed[1], M.fixed[2], M.fixed[3]);
        } else if (app != NULL) {
            size_t k = 0;
            for (const char *p = line; *p; p++) {
                if (p[0] == '^' && p[1]) {
                    p++;
                    keys[k++] = *p == '?' ? 0x7F : *p == '^' ? '^' : (char)(*p & 0x1F);
                } else {
                    keys[k++] = *p;
                }
            }
            if (moy_sh_app_keys(app, keys, k) == MOY_SH_APP_END) {
                moy_sh_app_close(app);
                app = NULL;
                printf("end\n");
            } else {
                show_last();
            }
        } else {
            printf("$ %s\n", line);
            line[n] = '\n';
            moy_sh_run(s, line, n + 1);
            show_last();
        }
        fflush(stdout);
    }
    fclose(f);
    if (app != NULL) {
        moy_sh_app_close(app);
    }
    moy_term_free(client);
    moy_sh_free(s);
    return 0;
}
