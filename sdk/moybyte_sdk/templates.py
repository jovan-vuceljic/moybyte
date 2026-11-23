"""The files `moy app new` writes, per tier (docs/app_api_v1.md section 1's
start-here table): each a program that runs as it is, using what its
manifest asks for and nothing more, so `moy app check` passes it clean."""

# An app on the UI tree (docs/app_api_v1.md section 1): the counter of
# tests/uitree_conformance/counter/, titled by the cart.
PY_APP = '''s = ui.state(count=0, loud=False)
ui.app(%(title_str)s, icon="calc")


def add():
    s.count += 1


def reset():
    s.count = 0


ui.action("add", "Add one", add)
ui.action("reset", "Reset", reset, when="count", off="grey")


def build():
    with ui.page(%(title_str)s):
        with ui.group("Count"):
            ui.info("Count", "{count}")
            ui.toggle("Loud", "loud")
            ui.link("add")
            ui.link("reset")
            ui.label("{count|plural press,presses} so far, {loud?loud:quiet}")
'''

LUA_APP = '''ui.app(%(title_str)s, { icon = "calc" })
local s = ui.state { count = 0, loud = false }

ui.action("add", "Add one", function() s.count = s.count + 1 end)
ui.action("reset", "Reset", function() s.count = 0 end, { when = "count", off = "grey" })

ui.page("counter", function()
  ui.group("Count", function()
    ui.info("Count", { value = "{count}" })
    ui.toggle("loud", { label = "Loud" })
    ui.link("add")
    ui.link("reset")
    ui.label("{count|plural press,presses} so far, {loud?loud:quiet}")
  end)
end, { title = %(title_str)s })
'''

# A compiled app on the UI tree: the counter of
# tests/uitree_conformance/counter/counter_wasm.moy, titled by the cart.
WASM_APP = '''#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

static int32_t s_count;

static void add(int32_t row) { uitree_set_int(s_count, uitree_get_int(s_count) + 1); }
static void reset(int32_t row) { uitree_set_int(s_count, 0); }

EXPORT(_init) void _init(void) {
    s_count = ut_int("count", 0);
    ut_bool("loud", 0);
    ut_action("add", "Add one", add);
    ut_action_when("reset", "Reset", "count", UT_OFF_GREY, reset);
    ut_page("counter", "%(title_c)s") {
        ut_group("Count") {
            ut_info("Count", "{count}");
            ut_toggle("loud", "Loud");
            ut_link("add", NULL);
            ut_link("reset", NULL);
            ut_label("{count|plural press,presses} so far, {loud?loud:quiet}");
        }
    }
    uitree_open();
}

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
'''

# A compiled cart, a game: one source that builds to main.wasm and to a
# native module per chip (moybyte/cart.h, sdk/README.md "A compiled cart").
CART_GAME = '''#include <stdint.h>

#include "moybyte/cart.h"

static const char TITLE[] = "%(title_c)s";
static int32_t x = 160, y = 120;

void init(void) {
}

void update(float dt) {
    (void)dt;
    x += moy_btn(MOY_RIGHT, 0) - moy_btn(MOY_LEFT, 0);
    y += moy_btn(MOY_DOWN, 0) - moy_btn(MOY_UP, 0);
    if (moy_btnp(MOY_B, 0)) {
        moy_quit();
    }
}

void draw(void) {
    moy_cls(1);
    moy_circ(x, y, 8, 8);
    moy_print(TITLE, sizeof TITLE - 1, 4, 4, 7);
}
'''

# A command: a WASI program or a native module, main and its exit code.
C_COMMAND = '''#include <stdio.h>

int main(int argc, char **argv) {
    printf("hello from %%s\\n", argc > 0 ? argv[0] : "%(title_c)s");
    for (int i = 1; i < argc; i++) {
        printf("  %%s\\n", argv[i]);
    }
    return 0;
}
'''

# A service, Python or Lua: it sleeps until a "ping" arrives and answers its
# sender with a "pong" (docs/app_api_v1.md sections 7 and 8).
PY_SERVICE = '''import moybyte


def moy_start():
    moybyte.on("ping", lambda sender, n: moybyte.send(sender, "pong", n + 1))
'''

LUA_SERVICE = '''function moy_start()
  moybyte.on("ping", function(sender, n)
    moybyte.send(sender, "pong", n + 1)
  end)
end
'''

# A compiled service, WASI or native: main waits on its event descriptor
# and answers each "ping" with a "pong"; end of file is its stop.
C_SERVICE = '''#include <poll.h>
#include <unistd.h>

#include "moybyte/os.h"

int main(void) {
    if (moy_on("ping", 1) < 0) {
        return 1;
    }
    static union {
        moy_evq_ev_t ev;
        char b[sizeof(moy_evq_ev_t) + 256];
    } m;
    for (;;) {
        struct pollfd p = { MOY_EVQ_FD, POLLIN, 0 };
        if (poll(&p, 1, -1) < 0) {
            return 1;
        }
        for (;;) {
            ssize_t n = read(MOY_EVQ_FD, &m, sizeof m);
            if (n == 0) {
                return 0;               // stopped
            }
            if (n < 0) {
                break;                  // nothing more queued
            }
            moy_send(m.ev.app, "pong", "[]");
        }
    }
}
'''
