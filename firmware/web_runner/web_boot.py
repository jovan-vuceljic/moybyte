"""Moybyte web runner boot (#151): the SHARED console under MicroPython-WASM.

The wasm RASTERIZES (moycore stage 4). This used to be the thinnest backend --
the system canvas was a `web_view.CommandCanvas` that recorded draw commands for
a JS replayer in the page, so the console never touched a pixel ("the browser is
the GPU"). That thesis is retired: the same `moy_gfx` + libmoy kernel the boards
run is compiled into this build, the canvas is literally `device_canvas.
DeviceCanvas` over the one-buffer compositor (`web_canvas.compositor`), and the page's only job is to
blit the finished RGB565 framebuffer. See web_canvas.py for why the boards'
class runs unmodified in a browser.

What that deleted, beyond the recorder itself: the whole /assets pixel payload.
The page needed the palette, the font, the cart's sheet/tilemap/images and every
shelf cover in order to replay commands -- shipped incrementally, memoised, and
re-requested through an `imgWant` latch, all of which was the runner's most
delicate machinery. None of those bytes cross any more; `assets_json` is now
metadata (size, title, audio rate, input hint) and nothing else.

The cart API is the shared pure-Python `host_api.make_api` -- the same backend
the PC sim runs -- and input replays through the shared `web_input.apply_events`
decode, so host == device == browser stays one code path.

Scope: the FULL console, both presentation tiers -- `can_manage=True`, so the
Make tile and the editors are reachable in the browser. Every write lands in the
browser's MEMFS first, and the sweep (`_build_watchers`) carries it to where the
page's store of record is: a site-mode page's OPFS -- the carts with their
journals and pmem, the drawings, and the console's own documents
(system/settings with the badges among its rows, the shared sheet), so a reload comes back on the same shelf,
theme, Settings and badges -- or the serving board for its carts, files,
portable Settings and badges (`moy_sync.SYSTEM_KEYS`; a board answering no
/console.json leaves them in the tab). A page with no OPFS keeps everything in
the tab and says so.

JS contract (see worker.js):
    boot(carts_root, cart=None, ...) -> build the Workstation
    assets_json()                 -> the page's metadata payload (JSON string)
    state_json()                  -> the dev channel's `state`, for a harness
    step_frame_json(dt, ahead)    -> tick one frame; "" when the redraw was
                                     skipped (#44 dirty gate), else a small
                                     JSON string; the PIXELS travel separately
    fb_addr() / fb_len()          -> the framebuffer's wasm-heap address and
                                     byte length, read by the worker
    apply_events_json(text)       -> queue an {"events":[...]} JSON text batch
                                     for the next step
    open_cart(name)               -> select+run a cart by folder name or title
    gpio_enable(pins_json)        -> the host answered POST /gpio: wire the
                                     pin verbs (absent otherwise -- see #9)
    gpio_poll_json() / gpio_ack_json(ok, text) / gpio_off()
"""

import gc
import json
from array import array

import console
import host_api
import layout_base
import moy_carts
import moy_catalogue
import page_link
import web_canvas
import web_input
import web_vfs
from moy_input import InputTable
from audio_session import PcmPump

_S = {}          # the runner singletons: ws / canvas / driver / sink
# The output's rate: the page's AudioContext's (audio_rate), so the page plays
# the samples one for one. The sessions mix at _MIX_RATE_HZ, as on every
# board, and the C upsamples that mix once to the output's rate
# (moy_aud_render_out); an MP3 is resampled once, in C, to it.
_MIX_RATE_HZ = 22050
_AUDIO_RATE_HZ = [_MIX_RATE_HZ]
_AUDIO_RATE_MIN, _AUDIO_RATE_MAX = 8000, 192000


def audio_rate(hz):
    """The page's AudioContext's sample rate, before boot: the output is made
    at it. 0 (no Web Audio) keeps the default."""
    hz = int(hz)
    if _AUDIO_RATE_MIN <= hz <= _AUDIO_RATE_MAX:
        _AUDIO_RATE_HZ[0] = hz


# The depth the page's sink is kept at: deep enough to ride out a late frame
# (wasm GC pause, phone jank) and the lag of the sink's count, shallow enough
# that a game sfx mixed into the stream isn't noticeably late.
_AUDIO_TARGET = 0.12
# The depth while the media service holds a stream (a station, a song), from
# its first chunk on: the frames that start one are the console's heaviest
# (the player's window and the bar's chip paint, the store's sweep of what it
# saved, the decoder's first frames), and a slow machine stalls over them,
# and now and then mid-stream, longer than _AUDIO_TARGET holds. Music is late
# by nothing anyone hears; a game's sounds keep _AUDIO_TARGET. Within what a
# 48 kHz context's decoded ring holds (moy_media.h, MOY_MEDIA_PCM_FRAMES), so
# the first chunk never pulls the decoder dry.
_AUDIO_MEDIA_TARGET = 0.25
_AUDIO_MAX_STEP = 0.25      # bound one frame's top-up render (seconds)


class _RunnerPump(PcmPump):
    """The page's pull of the kernel's mix, by count: the page's sink reports
    the samples it has played (`played`, step_frame_json's), the pull knows
    the ones it sent, and tick() renders what tops the difference up to
    _AUDIO_TARGET (_AUDIO_MEDIA_TARGET while a station or a song plays),
    so the stream is taken at the sink's own rate, a late frame eats depth
    and never the stream. Every sample rendered is sent, in
    order (`at` counts them), so the sink can tell an underrun from a gap.
    With no sink (`played` < 0) it renders rate*dt and sends nothing.
    Nothing is rendered while nothing sounds; the first chunk after that is
    `fresh`, a stream starting, not one the sink ran dry under. A frame's
    samples wait in `_buf` (`n` of them) for step_frame_json to hand the
    worker their address. A frame's pull allocates nothing: it runs every
    frame a stream plays."""

    def __init__(self):
        PcmPump.__init__(self, _MIX_RATE_HZ)
        out = _AUDIO_RATE_HZ[0]
        if self._na is not None:
            self._na.set_out_rate(out)
        self.rate = out
        self.played = -1
        self.sent = 0
        self.n = 0
        self.idle = True
        self.fresh = False
        self.at = 0                 # the samples take() handed over: the first's index
        self.starts = False         # and whether they start a stream
        self._target = int(out * _AUDIO_TARGET)
        self._media = int(out * _AUDIO_MEDIA_TARGET)
        self._cap = int(out * _AUDIO_MAX_STEP)
        self._buf = bytearray(self._cap * 2 + 64)
        self._mv = memoryview(self._buf)

    def tick(self, dt):
        na = self._na
        if na is None or not (na.active() or _media_open()):
            self.idle = True
            return
        if self.played >= 0:
            lead = self._media if _media_open() else self._target
            n = lead - (self.sent + self.n - self.played)
            if n > self._cap:
                n = self._cap
        else:
            n = self.frames(dt)
        room = len(self._buf) // 2 - self.n
        if n > room:
            n = room
        if n <= 0:
            return
        if self.idle:
            self.idle = False
            self.fresh = True
        mv = self._mv
        na.render_out(mv if self.n == 0 else mv[self.n * 2:], n)
        self.n += n
        self.rendered += n

    def take(self):
        """This frame's samples for the sink: their count, 0 when there are
        none or no sink; `at` is the first's index and `starts` whether they
        start a stream."""
        n = self.n
        self.n = 0
        if n <= 0 or self.played < 0:
            return 0
        self.at = self.sent
        self.sent += n
        self.starts = self.fresh
        self.fresh = False
        return n


_MEDIA = []


def _media():
    """The media service's module, None where the image has none."""
    if not _MEDIA:
        try:
            import moy_media
            _MEDIA.append(moy_media)
        except ImportError:
            _MEDIA.append(None)
    return _MEDIA[0]


def _media_open():
    """Whether the media service holds a stream: the mix then sounds with no
    session focused."""
    m = _media()
    return m is not None and m.pid() != 0


class _PointerSink:
    """Adapts the ConsoleDriver's DEFERRED touch state to the Pointer-shaped
    interface web_input.apply_events expects, so the browser drives the same
    event-decode path every other transport does."""

    def __init__(self, driver):
        self._d = driver

    def place(self, x, y):
        if self._d._click:
            self._d._after = (int(x), int(y))   # a press's frame keeps the press's place
        else:
            self._d.pointer.place(int(x), int(y))

    @property
    def down(self):
        return self._d._down

    @down.setter
    def down(self, v):
        if v and not self._d._down:
            self._d.ws.input_used("touch")      # a press: the input in use
        self._d._down = bool(v)
        self._d._buttons(1, bool(v))           # moy_input's PB_PRIMARY

    @property
    def hovers(self):
        return self._d.pointer.hovers

    @hovers.setter
    def hovers(self, v):
        self._d.pointer.hovers = bool(v)        # a mouse: it has a place with nothing held

    @property
    def click(self):
        return self._d._click

    @click.setter
    def click(self, v):
        if v:
            self._d._click = True
            self._d.ws.input_used("touch")


def _make_api(*a, **kw):
    """The shared cart API. No tier-specific gate any more, deliberately.

    This used to inject the pin backend itself, reading `_S["gpio"]` at cart
    start so the probe's timing and the cart's timing stayed independent. That
    worked and was wrong: it handed `pin_write` to EVERY cart the moment the
    serving host had pins, which is the capability half of the question with the
    consent half missing -- while cart_api's own comment said pins were gated
    "the same way as wifi and net", which have both halves. The backend is
    `ws.gpio` now and `player.start` gates it on the "pins" permission with its
    two siblings, so there is one gate rather than a second one over here.
    """
    return host_api.make_api(*a, **kw)


# The inputs a page declares (Workstation.use_inputs): its keyboard, the
# driver's "local" source; its on-screen gamepad, the "pad" source its holds
# name (web_input.PAD_SOURCE); and on a coarse-pointer page (a phone, a tablet)
# touch first, in use from boot, since a finger is what such a page is used
# with; a fine pointer is a mouse, no finger, as on the host. A gamepad held
# at the page joins them while one is connected (`_gamepad`).
WEB_INPUTS = (("local", "keys"), ("pad", "pad"))
WEB_TOUCH_INPUTS = (("touch", "touch"), ("local", "keys"), ("pad", "pad"))


def boot(carts_root=web_vfs.CARTS, cart=None, width=320, height=240,
         windowed=False, font_scale=0, hud=True, coarse=False, scheme=None,
         zoom=None, zooms=(0, 1)):
    """Build the shared Workstation over the RGB565 canvas + the VFS store.
    The page/harness wrote the cart bundle into `carts_root` before calling.

    `hud=False` suppresses the perf HUD -- see the note at the ws.show_fps
    assignment below for why a bundle would want that. `coarse` is the
    page's `(pointer: coarse)`: touch is then its input in use until a key
    is pressed (WEB_TOUCH_INPUTS). `scheme` is the page's colour scheme ("dark"
    or "light"): the theme variant of a first run, before the visitor has saved
    one (`console.wire_workstation_core`'s `first_variant`).

    Two presentation TIERS out of one wasm binary (the page picks per tab), and
    both are now the SAME arrangement their hardware twin uses:
      windowed=False -- the HANDHELD tier, i.e. the T-Deck's: ONE canvas, the
        system canvas IS the game canvas at 320x240, so composite_game is a
        no-op and the cart owns every pixel.
      windowed=True  -- the DESKTOP tier (#73/#105), i.e. the P4's: a big system
        canvas for the desk and its app windows, plus a separate 320x240 game
        canvas that `blit_game` composites into a window (integer-scaled through
        the same C kernel). Boots onto the desk with project management on.
        `zoom` (not None) makes its glass the page's that zooms: the UI size
        chosen (0: Auto) and `zooms` the choices (`Appearance.zoom_glass`),
        set before the stored settings apply, so the page's size stands.
    """
    # GC POLICY (surface model Phase B, the gate-0 finding): the port hardcodes
    # gc_alloc_threshold to 16KB, so EVERY painted frame schedules a FULL
    # collect at the next JS->Python boundary -- measured on the desktop tier:
    # ~67ms against its live set, i.e. the entire 70ms-vs-2.8ms window-drag gap
    # (quiet frames stay under 16KB and skip it, which is why idle was always
    # free). Raise the trigger so collects are RARE, and let the worker land
    # them on IDLE frames via idle_collect() below. Through sustained activity
    # the trigger itself bounds the heap: SPLIT_HEAP_AUTO grows the heap
    # instead of collecting only inside one call, and the trigger's collect
    # lands as the call that crossed it returns.
    #
    # 4MB (revised 2026-07-31 after measuring the collect itself). Earlier cuts
    # of this knob guessed in both directions and one regressed play: 24MB is
    # ABOVE the 16MB heap, so the threshold could never fire -- the split heap
    # just grew (16.3MB live after one drag, ~150MB reserved) and every later
    # collect scanned more. The measurement that settles it: an idle_collect
    # costs 5.7ms on the desk, 11ms after a 120-frame drag -- cheap. So collects
    # do not need to be rare, only OFF the gesture path: 4MB (~90 drag frames of
    # headroom at the post-attribution ~45KB/f) keeps memory bounded while the
    # worker's idle collect still lands them on quiet frames.
    import gc
    gc.threshold(4 * 1024 * 1024)
    if _S.get("store_mode") == "board" and "system" in (_S.get("seeded") or ()):
        _rebase_system(carts_root)
    carts = moy_catalogue.catalogue(carts_root)
    if windowed:
        # The system canvas is never smaller than the 320x240 game canvas it
        # composites in as a viewport (host_app.build_workstation clamps the
        # same way, for the same reason).
        width = max(320, int(width))
        height = max(240, int(height))
    # The boards' table, all sixteen names: a gamepad held at the page
    # presses what a board's does (web_input.BUTTON_NAMES).
    inp = InputTable()
    if not font_scale:
        # 1x on BOTH tiers (owner call): at 1024x600 the 2x system font ate the
        # desktop's density for no legibility win on a real monitor. The page can
        # still pass an explicit scale.
        font_scale = 1
    if windowed:
        # The P4's arrangement exactly: a big system canvas, a real 320x240 game
        # canvas beside it, and blit_game compositing one into the other through
        # the C kernel. The old recording tier could not do this -- it had no
        # pixels to composite, so a cart's commands shipped with a ["view", ...]
        # placement bracket (#175) for the page to honour, and a genuine
        # rasterizer here was unaffordable at ~85ms/frame interpreted.
        sysc = web_canvas.make_canvas(width, height, font_scale=font_scale)
        game = web_canvas.WebSystemCanvas(web_canvas.compositor(320, 240))
        ws = console.Workstation(host_api._NullComp(), game, inp, carts,
                                 sys_canvas=sysc, font_scale=font_scale,
                                 panel_diagonal_in=glass_in(width, height))
        if zoom is not None:
            ws.look.zoom_glass(int(zoom), tuple(zooms))
    else:
        sysc = game = web_canvas.make_canvas(320, 240, font_scale=font_scale)
        ws = console.Workstation(host_api._NullComp(), game, inp, carts)
    # Per-run cart canvas factory (SPEC.md 1/3.1): a cart declaring a smaller
    # raster (celeste's view(128, 120)) plays on its own off-screen canvas and
    # blit_game upscales it, same as both boards.
    ws.make_game_canvas = lambda w, h, owner=None: web_canvas.WebSystemCanvas(
        web_canvas.compositor(int(w), int(h)))
    # Cart runtimes: moycore, the SAME native module and glue the boards run --
    # third architecture, one engine. A build without the usermod still boots
    # (a lua cart opens the Player's runtime-missing panel). A compiled cart
    # runs on the browser's own WebAssembly engine (native/moy_wasm_web and the
    # worker's cart engine) through the same WasmRun a board uses.
    runtimes = {}
    try:
        from moycore_glue import make_runtimes
        runtimes = make_runtimes(ws)
    except ImportError:
        pass
    # The board-agnostic service wiring, in the one canonical order (host + both
    # boards + this runner).
    #
    # THE WIFI SERVICE is the serving Zero's own, where the worker's probe of
    # its sealed /wifi answered (`wifi_enable`, wifi_link.BoardWifi): the
    # panel, the bar's glyph and the Settings row are that board's. Anywhere
    # else there is NONE, and that is the honest answer rather than a missing one.
    # This wired host_api's FakeWifi until 2026-08-30 -- the SIMULATOR's stand-in,
    # whose whole job is to invent four access points ("Home WiFi", "Coffee
    # Shop", "Neighbor 5G", "Library Guest") and a 192.168.1.42 so the desktop's
    # WIFI panel can be developed with no radio. On a page SERVED BY A BOARD that
    # is not a stand-in, it is a lie: the Zero is headless, so this panel is the
    # only WIFI screen that board has, and it listed networks that do not exist
    # and accepted a join that went nowhere. Reported from a real session.
    #
    # `None` is the shape every other absent capability uses here, and the shell
    # already knows it -- settings_layer says NO WIFI SERVICE and stops. A page
    # cannot reach a radio, and the day it can it will be through a bridge to the
    # board's own service (as gpio_link and update_link are), not a fake.
    console.wire_workstation_core(
        ws, moy_carts, carts_root, _make_api,
        _S.get("wifi"),
        audio_out=_RunnerPump(), runtimes=runtimes, can_manage=True,
        pointer=console.Pointer(sysc.w, sysc.h), inp=inp, first_variant=scheme)
    # AUTHORING IS ON, BOTH TIERS (owner call): the browser build is the whole
    # console, not the player-only runner #151 originally scoped -- the Make tile
    # and the editors are the point. This used to add "and nothing persists
    # across a reload", which #193 made false: a static-host page keeps carts in
    # OPFS and a board-served one writes them home. What stays in the tab is
    # everything in a browser with no usable OPFS -- and the page says THAT out
    # loud -- and the Settings a board keeps for itself (moy_sync.SYSTEM_KEYS),
    # or all of them and the badges where the board serves no /console.json.
    # can_manage is wired AFTER the launcher was built, so rebuild the shelf for it
    # to appear.
    ws.launcher.items = ws.home.launcher_items(ws.carts.all)
    # Get Carts (#124), by where this page's carts live (`_cart_seams`).
    seams = _cart_seams(ws, _S.get("store_mode"), carts_root)
    ws.cart_net = seams[0]
    ws.cart_keep = seams[1]
    ws.cart_pick = seams[2]
    ws.cart_home = seams[3]
    ws.cart_board = seams[4]
    ws.cart_own = _S.get("cart_own") if seams[0] is not None else None
    ws.media_net = _media_net(ws, _S.get("store_mode"), carts_root)
    # The Moybyte shell's achievements are gamification for the kid console,
    # which the console page is, as on a board; they are no part of the
    # one-cart player (`cart`: an export, the gallery, a kiosk bundle), whose
    # frames are the cart's. The shell's own sends go quiet (`ws.ach.mute`:
    # opening the cart would be "First Steps"), and no find raises the
    # banner, which console.py's own _draw_toast renders.
    if cart:
        ws.ach.mute = True
        ws.ach.toast = None
        ws.notices.achievement_unlocked = lambda *a, **k: None
    # The Pointer boots visible (a device shows the trackball cursor until its
    # idle timeout) -- in the browser that composited an arrow over the first
    # game frames (owner report: "a cursor flashes at open"). Start hidden; a
    # real trackball-style pan on a system surface re-shows it, a mouse/touch
    # place() keeps it hidden as always.
    ws.pointer.visible = False
    if windowed:
        # Installed LAST so it anchors its root context -- and its per-window
        # content buffers, via root.new_layer -- to the system canvas, where
        # the desk fits (Workstation.place_tier). Two worlds (#105): boot onto
        # the desk.
        from wm_windowed import WindowedWM
        ws.windowed_wm = WindowedWM
        ws.place_tier()
    # HUD (perf_hud.PerfHud): the bottom-right FPS chip draws onto the GAME
    # canvas, so on the handheld tier -- where the system canvas IS the game
    # canvas -- it lands inside the cart's own 320x240 raster and ships in the
    # cart's own command stream. That is host chrome sitting in a frame the cart
    # owns, and it is wrong anywhere the frame IS the product: a spec
    # conformance capture (moy SPEC.md 11 makes this player the golden-frame
    # tiebreaker, and a golden frame must not contain an FPS counter) or a
    # published web export of somebody's game.
    #
    # Found by moy-spec's conformance harness, which measured this player against
    # the suite and got exactly 200 differing pixels on every scene -- a 20x10
    # box at (299, 229), which is the chip.
    #
    # A caller that wants clean frames passes hud=False. Otherwise the chip is
    # the Settings SHOW FPS row's, as on a board: the boot's settings apply
    # (wire_workstation_core) already set it from the stored settings.
    if not hud:
        ws.show_fps = False
        ws.perf_hud = False
    driver = host_api.ConsoleDriver(ws, own_repeat=True)   # the browser repeats its keys
    ws.use_inputs(WEB_TOUCH_INPUTS if coarse else WEB_INPUTS)
    ws.soft_keyboard = True     # the page's ⌨ summons the browser's keyboard
    ws.panel_light = False      # no light to set: Brightness is not offered
    # The page around the console: its asks and its word (page_link.py). A
    # page a console serves plays a cart on that console's glass too.
    ws.page = page_link.PageLink(served=_S.get("store_mode") == "board", play=open_cart)
    _S["ws"] = ws
    # The pin backend, if the worker's probe found one. Stashed by gpio_enable
    # (which runs BEFORE this, since the probe is answered while the console is
    # still being built) and hung on the Workstation HERE, because `ws.gpio` is
    # the seam the Player gates on -- beside ws.wifi and ws.net, in one place.
    ws.gpio = _S.get("gpio")
    # The 3.4 sync push (moy_sync): watch this VFS store for committed changes
    # and hand them to the worker as wire batches; the worker POSTs them to
    # the relative /sync of whoever served the page. Constructed AFTER the
    # pull wrote the store, so the baseline is "the board's own state, nothing
    # pending". A page served by a host with no /sync (moybyte.com, an
    # export) gets one failed POST and the worker calls sync_off().
    # ONE watcher per registered sync root (moy_sync.SYNC_ROOTS) -- built by
    # ITERATING the registry, so a new store is watched the day it is registered
    # with no new line here. THE JOURNAL FOLLOWS THE STORE OF RECORD (2026-08-25):
    # `root.watch_skip(site)` sweeps journal/ into the browser's own OPFS in SITE
    # mode for the root that is of record there (carts), and keeps the wire's own
    # rule everywhere else -- so a board-mode sweep is byte-identical to what it
    # always was. A root whose store is not present in the VFS (a sibling root
    # the served host has no layer for) simply gets no watcher, and neither does
    # a root the worker did not seed (the console's own documents, where the
    # board serves no /console.json).
    _S["watchers"] = _build_watchers(carts_root, _S.get("store_mode") == "site",
                                     _S.get("seeded"))
    # The canvas the PAGE presents: the system canvas on the desktop tier, the
    # one shared canvas on the handheld tier. Its buffer is what fb_addr()
    # publishes, so this is the single place the two tiers differ downstream.
    _S["canvas"] = sysc
    _S["driver"] = driver
    au = ws.audio_out
    _S["pump"] = au if isinstance(au, _RunnerPump) else None
    _S["pcm_buf"] = None
    _S["sink"] = _PointerSink(driver)
    _S["root"] = carts_root
    _S["exit"] = ws.spine.exit_to_caller     # the real exit (reload_cart uses it)
    _site_carts_made(ws)
    if cart:
        open_cart(cart)
    return True


def _site_carts_made(ws):
    """The carts this page got from the site that serves it are its console's
    own, seeded like a board's: each is recorded as made on this console
    (`Consent.made`), so its first run asks nothing. They are the folders the
    seed found in the served bundle (`moy_sync.served_carts`), or every cart
    on the shelf when no seed ran (the bundle went whole into a store with
    no OPFS: mode "none"). A board's page runs the board's carts under the
    board's records, and a cart dropped onto the page arrived as files:
    asked on its first run."""
    if _S.get("store_mode") not in ("site", "none"):
        return
    import app_perms
    import moy_sync
    served = moy_sync.served_carts()
    ws.consent.made(*[app_perms.app_id(c) for c in ws.carts.all
                      if served is None
                      or (c.get("path") or "").rsplit("/", 1)[-1] in served])


def _cart_seams(ws, mode, root):
    """(cart_net, cart_keep, cart_pick, cart_home, cart_board) for Get Carts
    (#124), by the page's mode, which is where its carts live.

    BOARD: the carts this page shows are the serving console's, and that
    console gets its own -- with its own module for its own chip, and while
    this page is connected its glass is parked, so the two never install side
    by side. The page fetches nothing and the app says where carts come from
    ("board"; `update_enable` learns whether that console has a screen); one
    that answered the /official probe (`official_enable`) installs carts
    when this page asks (`carts_link.BoardCarts`).
    SITE: the page's own store, so the page's fetch is the network and OPFS
    keeps what lands (`carts_link`). NONE (no OPFS): the same network, and an
    install lives in this tab like every other edit here, which the page
    already says out loud. Both check a signed index under the release keys
    the bundle bakes in (`release_keys`, cart_index.INDEX_KEYS) and list
    the official carts of the release indexes.json names (`ws.cart_own`,
    set by `boot`)."""
    if mode == "board":
        board = None
        link = _worker_link(ws, mode) if _S.get("official") else None
        if link is not None:
            import carts_link
            board = carts_link.BoardCarts(link, root)
        return None, None, None, "board", board
    link = _worker_link(ws, mode)
    if link is None:
        return None, None, None, None, None
    import cart_index
    try:
        import release_keys
        cart_index.INDEX_KEYS = tuple(release_keys.KEYS) or None
    except ImportError:              # a bundle staged without them
        pass
    import carts_link
    keep = carts_link.WebCartKeep(link) if mode == "site" else None
    return carts_link.WebCartNet(link), keep, link.pick, None, None


def _worker_link(ws, mode):
    """The queue to the worker's pump (`carts_link.CartsLink`), one a page:
    Get Carts' fetches and keeps in a page that keeps its carts, Music's
    reads in every page. None before a mode is known."""
    if _S.get("carts") is not None:
        return _S["carts"]
    if mode not in ("site", "none", "board"):
        return None
    try:
        import carts_link
    except ImportError as exc:       # never block a boot
        print("carts link unavailable:", exc)
        return None

    def _wake():
        ws.mark_dirty()
    link = carts_link.CartsLink(wake=_wake, landed=_cart_landed)
    _S["carts"] = link
    return link


def _media_net(ws, mode, carts_root):
    """`ws.media_net` (media_link.py): the songs and URLs Music plays from
    the page's bytes -- the browser's OPFS songs or the serving board's, and
    the page's fetch -- where the media service is in the image."""
    link = _worker_link(ws, mode)
    if link is None:
        return None
    if _media() is None:
        return None
    try:
        import media_link
        from moy_store_base import files_root
    except ImportError:
        return None
    import moy_sync
    return media_link.WebMediaNet(link, files_root(carts_root) + "/" + moy_sync.MUSIC)


def _cart_landed(folder):
    """A cart the keeper made durable moved into the carts folder: its files
    are not news for the sweep (OPFS already holds them, binary module and
    all, which the sweep could never carry), and the shelf shows it."""
    w = (_S.get("watchers") or {}).get("carts")
    if w is not None:
        w.adopt(folder)
    _rescan()


def carts_poll_json():
    """What the worker's carts pump should start or stop, or ""."""
    link = _S.get("carts")
    return link.poll_json() if link is not None else ""


def carts_event_json(text):
    """An answer from the worker: a response head or end, a keeper's verdict,
    a picked file, the store's room."""
    link = _S.get("carts")
    if link is not None:
        link.event_json(text)
    return ""


def _rebase_system(carts_root):
    """The pulled settings' cart folders under this VFS's `carts_root` (they
    cross as folder names, `moy_sync.CART_PATH_KEYS`), before the Workstation
    reads them."""
    import moy_sync
    path = moy_sync.system_root(carts_root) + "/" + moy_sync.SYSTEM_SETTINGS
    try:
        with open(path) as f:
            text = moy_sync.rebase_system(f.read(), carts_root)
        with open(path, "w") as f:
            f.write(text)
    except OSError:
        pass                             # nothing pulled: the defaults


def _build_watchers(carts_root, site, seeded=None):
    """`{root_id: StoreWatcher}` for every registered sync root whose store is
    PRESENT in the VFS. A missing store means no watcher -- and that is a
    CAPABILITY signal, not a bug: worker.js seeds a sibling root's directory only
    when its source exists (a board-served `files.json`, or the browser's own
    OPFS in site mode), so a host that has no files layer leaves no directory,
    gets no files watcher, and never aims a files batch at a receiver that could
    only refuse it. `seeded` is the worker's list of the roots it seeded: the
    system root's directory is the carts folder's parent, present whatever the
    host serves, so a board-served page watches it only when the board answered
    /console.json and the worker said so -- firmware without it refuses the
    batch. Never blocks a boot -- any failure leaves an empty dict."""
    import os
    out = {}
    try:
        import moy_sync
        for root in moy_sync.SYNC_ROOTS:
            if site and not root.site:
                continue                 # another keeper writes it here
            if seeded is not None:
                if root.id not in seeded:
                    continue             # the host does not serve it
            elif root.top is not None and not site:
                continue                 # its directory proves nothing
            path = root.path(carts_root)
            if path is None:
                continue                 # no such layer on this host at all
            try:
                os.stat(path)            # present in the VFS?
            except OSError:
                continue                 # not seeded -> not watched
            out[root.id] = moy_sync.StoreWatcher(
                path, root_id=root.id, skip=root.watch_skip(site),
                top=root.watch_top(site), read=root.watch_read())
    except Exception as exc:  # noqa: BLE001 -- sync must never block a boot
        print("sync watcher unavailable:", exc)
        return {}
    return out


def _watchers():
    """The live watchers, in REGISTRY (drain) order -- CARTS FIRST, a deliberate
    priority: a cart edit is what the kid is watching on the glass, and a drawing
    landing a second later costs nobody anything. Order comes from the registry,
    never the dict (MicroPython dicts are not insertion-ordered)."""
    import moy_sync
    ws = _S.get("watchers") or {}
    return [ws[r.id] for r in moy_sync.SYNC_ROOTS if r.id in ws]


def page_boot(carts_root, query_json, coarse=False, scheme=""):
    """`boot` the console a page's address asks for (`query_json`: its query
    string's pairs), on the page's `(pointer: coarse)` and its colour scheme
    ("dark" or "light"; anything else is the default). Call `page_start`
    after anything else that needs the live console (`update_enable`).

    TIER SELECT (#73/#175). The DESKTOP desk is the default everywhere (owner
    call 2026-08-14) -- on moybyte.com and on a board serving its own console
    alike. It was the handheld 320x240 tier, which made the full-size product
    the thing you had to know a url parameter to see.
      ?handheld=1  the 320x240 console (the phone-shaped one)
      ?size=WxH    the glass's size (1024x600); the page passes its own,
                   live, unless its address names one, which stays fixed
      ?zoom=N&zooms=0,N,..  the glass zooms: the UI size chosen (0: Auto)
                   and the choices, as percents (`Appearance.zoom_glass`)
      ?cart=NAME   that cart; a bundle of one cart names it without asking
      ?desktop=1   the desk even with a cart named
      ?console=1   start in console mode (the desk's PLAY), the windows' tier
      ?meter=1     the VM heap's allocation counted each frame (`_METER`)
      ?linkcheck=1 the match's world check armed on the board's radio link
                   (`live_pump`), as the dev channel's `link check on` arms
                   a console's
    A single ?cart=<name> still implies handheld: that url is the one-cart
    player (moy export / the gallery), where a desk around one game is chrome
    nobody asked for. The served carts are the bundle's
    (`moy_sync.served_carts`), else the shelf's."""
    import moy_sync
    q = json.loads(query_json)
    if q.get("meter"):
        _METER[0] = 1
    _S["linkcheck"] = bool(q.get("linkcheck"))
    names = moy_sync.served_carts()
    if names is None:
        names = json.loads(moy_sync.folders_json(carts_root))
    cart = q.get("cart") or (names[0] if len(names) == 1 else None)
    desktop = not q.get("handheld") and bool(q.get("desktop") or not cart)
    scheme = scheme if scheme in ("dark", "light") else None
    if desktop:
        w, h = 1024, 600
        size = q.get("size") or ""
        wh = size.split("x")
        if len(wh) == 2 and wh[0].isdigit() and wh[1].isdigit():
            w, h = int(wh[0]), int(wh[1])
        zoom = q.get("zoom")
        zooms = tuple(int(z) for z in (q.get("zooms") or "0,1").split(",") if z.isdigit())
        boot(carts_root, None, w, h, True, coarse=coarse, scheme=scheme,
             zoom=int(zoom) if zoom is not None and zoom.isdigit() else None,
             zooms=zooms or (0, 1))
    else:
        boot(carts_root, cart=cart, coarse=coarse, scheme=scheme)
    _S["page_start"] = (q.get("edit"), q.get("tab"), bool(q.get("play")),
                        desktop, cart, len(names), bool(q.get("console")),
                        q.get("only") == "desk")
    return ""


def page_start():
    """What a page's address starts the console on (after `page_boot`):
    ?edit=<cart>[&tab=code|paint|map|...][&play=1] opens that cart in the
    Editor (`start_edit`), where a plain visit lands on the home, and with
    play=1 presses its Play; with &only=desk it does so only where the
    console lands on the desk, and in console mode (a phone) the visit lands
    on the home; a desk with a cart named opens it; and the
    one-cart player of a bundle of one cart is a kiosk -- the exit gesture
    restarts the game instead of dropping into the shell, because the game
    IS the page. ?console=1 starts the desk in console mode (its PLAY)."""
    edit, tab, play, desktop, cart, served, cons, only_desk = _S.pop("page_start")
    if cons and getattr(_S["ws"].wm, "mode", None) == "desktop":
        _S["ws"].wm.enter_console()
    if only_desk and getattr(_S["ws"].wm, "mode", None) != "desktop":
        edit = None
    if edit:
        start_edit(edit, tab or None, play)
    if desktop and cart:
        open_cart(cart)
    if not desktop and served == 1 and cart:
        kiosk(cart)
    return ""


def kiosk(name):
    """Single-cart bundle mode (the spec export): the game IS the page. The
    exit gesture RESTARTS the cart instead of dropping into the console shell
    -- a PICO-8 web export has no shell, and neither should this."""
    ws = _S["ws"]
    real_exit = _S["exit"]

    def _restart():
        real_exit()
        open_cart(name)
    ws.spine.exit_to_caller = _restart


def _rescan():
    """Re-derive the shelf from the store on disk, through the ONE body every
    other roster change already runs -- `CartManager.apply`.

    It used to hand-roll that: set `carts.all`, rebuild `launcher.items`, slim.
    This copy was written 2026-08-25, two days BEFORE the #209 carve made
    `apply` the single body for create/duplicate/delete and the board's sync
    re-scan -- and living outside `runtime/`, it was the one caller that sweep
    did not reach. It then drifted three ways, each of which reached a user:

      * it never rebuilt the PICKER, so a cart imported in the browser appeared
        on the launcher and was MISSING from Projects (#194, reported on the
        hosted console). `edit_cart`'s own docstring says an imported cart
        arrives "exactly like an authored one", and the grid disagreed.
      * it never invalidated the cover caches, and `slim()` bakes each icon and
        then deletes the art it was baked FROM -- the exact ordering `apply`
        calls out, where clearing nothing lets a stale entry become permanent.
      * it used `_launcher_items` where `apply` uses `_launcher_view_items`,
        dropping an active search filter (#105).

    `apply` also keeps the old shelf when a scan comes back empty rather than
    blanking it, which is its deliberate failure direction and now this one's."""
    ws = _S["ws"]
    ws.carts.apply(moy_catalogue.catalogue(_S["root"]))
    ws.mark_dirty()


def rescan_store():
    """Files landed in the VFS from OUTSIDE the console -- the page's .moy
    import (#193). Re-scan the shelf, and deliberately do NOT rebase the sync
    watcher: an import is a CHANGE, so it must stay pending and reach the store
    (the browser's OPFS in mode 1) on the next sweep like any other commit.
    reload_cart's rebase is the opposite case -- there the files arrived FROM
    the far end, and replaying them back at it would undo the reload."""
    _rescan()
    return True


def reload_cart(name=None):
    """Dev hot-reload (the moy CLI's watch loop): the page rewrote changed cart
    files in the VFS; pop any running cart (flushes pmem via release_world),
    re-scan the store, and restart `name` (default: the cart that was running).
    Returns True when a cart restarted."""
    ws = _S["ws"]
    cart = getattr(ws, "cart", None)
    if name is None and cart is not None:
        name = (cart.get("path") or "").rsplit("/", 1)[-1]
    if cart is not None:
        _S["exit"]()          # the REAL exit (kiosk wraps ws.spine.exit_to_caller)
    _rescan()
    for w in _watchers():
        # The reload just re-pulled the served store over the VFS -- adopt it as
        # the new baseline (deliberate LWW: replaying local unpushed edits over a
        # state the human just asked for would undo the reload).
        w.rebase()
    return open_cart(name) if name else True


def _select_cart(name):
    """Bring the cart `name` names (folder name with or without `.moy`, or
    manifest title) up on the home -- the tab that holds it, then its card.
    True when it landed on one."""
    ws = _S["ws"]
    want = str(name).lower()
    if want.endswith(".moy"):
        want = want[:-4]
    for c in ws.home.runnable_items():
        folder = c.get("path", "").rsplit("/", 1)[-1].lower()
        if folder.endswith(".moy"):
            folder = folder[:-4]
        if want in (folder, c.get("title", "").lower()):
            return ws.home.select_cart(c)
    return False


def open_cart(name):
    """Select + run a cart by folder name ('moybyte.star_catcher.moy', extension
    optional) or manifest title, skipping the launcher -- the single-cart-embed
    path (?cart=...). Unknown name -> False (the shelf stays up)."""
    if not _select_cart(name):
        return False
    _S["ws"].open()
    return True


_EDIT_TABS = {"paint": "open_paint", "map": "open_map", "music": "open_music",
              "scene": "open_scene", "blocks": "open_blocks"}


def edit_cart(name, tab=None):
    """Open a cart in the EDITOR, landing on its tabs with its own assets --
    the "open in editor" half of the p8 drop (#194).

    The tap that RUNS a cart and the one that EDITS it are different verbs in
    the shell (shell_ux_v1.md §4: a tap on Make edits, on the other tabs it
    runs), and this is the edit one -- the same entry Make uses, so an imported
    cart arrives in the Sprites / Map / Music tabs exactly like an authored one.
    `tab` lands on one of them ("paint"/"map"/"music"/...) instead of the
    default Config landing.

    Returns a small JSON state so the caller can SEE it landed rather than
    assume: an editor that silently did not open looks identical to one that
    did until somebody screenshots it."""
    ws = _S["ws"]
    # END any run FIRST, and before the launcher selection is moved. On the
    # windowed desk a cart plays in its own window, so an editor opened over a
    # still-running import leaves the game sitting on top of the code it is
    # meant to show -- and the run's world would outlive the workspace the
    # Editor rebuilds. PLAY in the Editor is how it starts again.
    if getattr(ws, "cart", None) is not None:
        _S["exit"]()              # the REAL exit (kiosk wraps ws.spine.exit_to_caller)
    ok = _select_cart(name)
    if ok:
        ws.open_in_editor()
        opener = _EDIT_TABS.get(tab)
        if opener is not None:
            getattr(ws.editor_app, opener)()
        elif tab:
            ws.text.set_menu_view(tab)         # a tab with no opener of its own (code)
    return json.dumps({
        "ok": ok,
        "screen": getattr(ws, "screen", None),
        "tab": getattr(ws, "menu_view", None),
        "title": _cart_title(),
    })


def start_edit(name, tab=None, play=False):
    """The start option (`?edit=<cart>&tab=<tab>&play=1`): boot into the
    Editor on `name`'s `tab` where a plain visit boots to the home. It is
    `edit_cart` without the First Steps badge -- opening the editor was the
    page's doing, not a thing the visitor did, and a banner over the first
    frame would hide the code the start option is there to show. On the desk
    the Editor is a window, the desk around it in sight, unless this browser
    left it full screen (`win_full`); `play` presses its Play, which on the
    desk runs the cart in the Editor's Game pane. Returns edit_cart's JSON."""
    ws = _S["ws"]
    was, ws.ach.mute = ws.ach.mute, True
    try:
        got = edit_cart(name, tab)
    finally:
        ws.ach.mute = was
    left = ws.system.get("win_full", None)
    restore = not (isinstance(left, dict) and "menu" in left)
    play = play and json.loads(got)["ok"]

    def settle():
        # The Editor's window is made by the frame after the open, so this
        # runs at that frame's tail.
        wm = ws.wm
        win = getattr(wm, "windows", {}).get("menu")
        if restore and win is not None and win.full():
            wm.toggle_max(win)
        if play:
            ws.text.leave_menu()
    ws.defer(settle, toast=play)
    return got


def drop_kind(name, head_json):
    """What a file dropped on the page is, from its name and its first bytes
    (`head_json`, a JSON list of them): "song" for one Music keeps
    (moy_sync.local_song), "p8" for a PICO-8 cart, else "archive" (a `.moy`
    export, a zip). A text cart is known by its name, a `.p8.png` by its
    bytes too: a BBS cart saved by a person is named anything, and the only
    other thing the page imports is a zip, so a PNG is a cart attempt and
    `png_problem` says so kindly when it is a holiday photo."""
    import moy_sync
    base = name.rsplit("/", 1)[-1]
    if moy_sync.local_song(moy_sync.MUSIC + "/" + base):
        return "song"
    low = base.lower()
    if low.endswith(".p8") or low.endswith(".p8.png"):
        return "p8"
    import p8_writer
    return "p8" if p8_writer.looks_like_png(bytes(json.loads(head_json))) else "archive"


def import_p8_json(path, name, root):
    """Convert a dropped PICO-8 cart at `path` into a `.moy` folder (#194) in
    the store `root`, named by the store's import rule
    (moy_carts.import_base): web_p8's report, with the folder as `dir`.

    Lazily imported so the console boots without the converter in RAM: a session
    that never drops a cart never pays for it."""
    import web_p8
    out_dir = moy_carts.import_target(root, moy_carts.import_base(name))
    r = json.loads(web_p8.import_p8_json(path, name, out_dir))
    r["dir"] = out_dir.rsplit("/", 1)[-1]
    return json.dumps(r)


def import_archive_json(path, name, root):
    """A dropped `.moy` archive at `path` onto the shelf `root`
    (moy_carts.import_archive), the archive removed after: {"dir": the
    folder it landed in} or {"error": why not}."""
    import os
    try:
        got = moy_carts.import_archive(path, root, name=name)
    except Exception as exc:  # noqa: BLE001 -- a bad zip is a message
        got = exc
    try:
        os.remove(path)
    except OSError:
        pass
    if isinstance(got, Exception):
        return json.dumps({"error": str(got) or "not a zip file"})
    if got is None:
        return json.dumps({"error": "nothing in that zip looked like a cart"})
    return json.dumps({"dir": got.rsplit("/", 1)[-1]})


def export_cart(path, dest):
    """The cart folder at `path` packed to `dest` as a `.moy` archive
    (moy_carts.pack, the wire's skip rule): the number of files."""
    return moy_carts.pack(path, dest)


def _cart_title():
    cart = getattr(_S["ws"], "cart", None)
    return cart.get("title") if cart is not None else None


def _audio_rate():
    return _AUDIO_RATE_HZ[0]


def assets_json():
    """The page's METADATA -- no pixels.

    This used to be the runner's heaviest and most delicate call: the page
    replayed draw commands, so it needed the palette, the petme128 blob, the
    open cart's sheet and tilemap, every paint image and every shelf cover,
    base64'd into one payload. Serialising it cost 360-560ms (json.dumps over
    ~644KB), which meant a memo keyed on a cover generation, an incremental
    "ship only what this client lacks" diff, a re-request latch in the page for
    images a draw referenced but the client did not hold, and a documented trap
    where returning the previous payload on a memo miss shipped a stale input
    hint. All of it existed to move pixels the wasm can now draw itself, and all
    of it is deleted with the replayer.

    What the page still cannot derive: how big the surface is, what the cart is
    called, the audio rate its worklet resamples to, which on-screen controls to
    show, and how this build orders the bytes of a 565 pixel (below).
    """
    ws = _S["ws"]
    ws.mark_dirty()                 # the reloaded page wants a full frame
    cv = _S["canvas"]
    return json.dumps({
        "v": 3,
        "w": cv.w, "h": cv.h,
        "cart": _cart_title(),
        "audio_rate": _audio_rate(),
        "input": web_input.effective_input_kinds(ws),
        # BYTE ORDER of the RGB565 framebuffer, reported rather than assumed.
        # device_canvas picks its palette table from the PANEL it is talking to:
        # canonical little-endian for the P4's DSI scan-out, byte-swapped for the
        # T-Deck's SPI panel (which folds the swap into the LUT so the driver can
        # skip a ~17ms/frame CPU pass). A browser has no panel, and this build
        # takes whichever branch the probe lands on -- so the page builds its
        # 565->RGBA table from this flag instead of guessing, and stays correct
        # if the probe ever changes.
        "swap": 0 if _wire_is_canonical() else 1,
    })


def _wire_is_canonical():
    """True when the framebuffer holds little-endian RGB565."""
    try:
        import device_canvas
        return device_canvas.PAL565_WIRE is device_canvas.PAL565
    except Exception:  # noqa: BLE001 -- unknown -> assume canonical
        return True


def fb_addr():
    """The presented framebuffer's address in the wasm heap.

    The worker reads the finished frame straight out of `Module.HEAPU8` at this
    offset, so a painted frame costs one memcpy on the JS side and nothing at
    all on the Python side. Re-read every frame rather than cached: a resize
    builds a new canvas, and MicroPython's own heap can move under us in ways
    this module has no business tracking.
    """
    import uctypes
    return uctypes.addressof(_S["canvas"]._buf)


def fb_len():
    """The framebuffer's length in BYTES (w * h * 2)."""
    return len(_S["canvas"]._buf)


# The VM heap's allocation, counted on a page that asks (?meter=1) for a
# harness to read (`state_json`'s `alloc`): `step` the bytes the frames'
# steps allocated over `frames` of them, `loop` what the worker's loop
# allocated between two steps (its pumps, the store's sweep, the answers it
# hands in) over `gaps` of them. An interval a collection ran in shrinks the
# heap and is not counted. Off, it costs a list read a frame: each count is
# a walk of the heap's allocation table (gc.mem_alloc).
_METER = [0]
_ALLOC = {"step": 0, "frames": 0, "loop": 0, "gaps": 0, "at": 0}


def step_frame_json(dt, played=-1):
    """Advance the console one frame (`_step`), metered where `_METER`."""
    if not _METER[0]:
        return _step(dt, played)
    m = _ALLOC
    a0 = gc.mem_alloc()
    if m["at"] and a0 >= m["at"]:
        m["loop"] += a0 - m["at"]
        m["gaps"] += 1
    r = _step(dt, played)
    a1 = gc.mem_alloc()
    if a1 >= a0:
        m["step"] += a1 - a0
        m["frames"] += 1
    m["at"] = a1
    return r


def _step(dt, played):
    """Advance the console one frame.

    Returns "" when the console skipped the redraw (#44 dirty gate: nothing
    moved) -- the page then simply keeps the pixels it already has. Otherwise
    a small JSON string carrying what does not live in the framebuffer:
    whether it painted, the cart title and the input hint, and where a copy
    changed the console's clipboard its text (`clip`), which a frame that
    did not paint carries too (its `paint` 0). `played` is the
    page's sink's count of samples played (-1 = no sink): _RunnerPump tops
    its depth up from it.

    The PIXELS and the SAMPLES are not in here. The worker reads the pixels
    from fb_addr()/fb_len() when `paint` is set, and this frame's samples
    from the four numbers at pcm_addr() (`_PCM`): how many, their index in
    the stream, whether they start one and their heap address. A frame that
    only moves samples (a station playing on behind a still desk) returns ""
    and allocates nothing here.
    """
    ws = _S["ws"]
    au = _S.get("pump")
    if au is not None:
        au.played = int(played)
        pulled = au.rendered
    painted_before = ws.frame_state.frames_drawn
    _feed_events()
    _S["driver"].frame(dt)
    painted = ws.frame_state.frames_drawn != painted_before
    clip = _clip_out()
    pcm = _PCM
    pcm[0] = 0
    if au is not None:
        if au.rendered == pulled and _media_open():
            # The media stream sounds with no Player pulling the mix (the
            # shell, an app): a board's feeder task pulls it, the page's
            # frame here.
            au.tick(dt)
        n = au.take()
        if n:
            pcm[0] = n
            pcm[1] = au.at
            pcm[2] = 1 if au.starts else 0
            pcm[3] = _pcm_buf(au)
    zoom = ws.look.zoom
    moved = zoom != _ZOOM[0]
    _ZOOM[0] = zoom
    page = ws.page
    asks = page.drain() if page is not None else None
    if clip is None and asks is None and not moved and not painted:
        return ""
    cv = _S.get("canvas") or ws.sys_canvas
    out = {"paint": 1 if painted else 0, "cart": _cart_title(),
           "input": web_input.effective_input_kinds(ws), "w": cv.w, "h": cv.h}
    if clip is not None:
        out["clip"] = clip
    if asks is not None:
        out["ask"] = asks
    if zoom is not None:
        out["zoom"] = zoom
    return json.dumps(out)


# The UI size of the last frame (`zoom` in every frame's JSON on a zoomed
# glass, 0: Auto): Settings' UI size row's, which the page keeps per browser
# and divides its viewport by. A frame where it moved is sent painted or not;
# every frame names it, since the page keeps only the newest frame.
_ZOOM = [None]


def glass(w, h, zoom, zooms):
    """The page's viewport changed (a resize, a rotation, a UI size the page
    took from a frame): the glass at `w` x `h` (`Workstation.resize_glass`,
    the diagonal `glass_in` declares), `zoom` the UI size chosen (0: Auto)
    and `zooms` the choices this viewport offers Settings' UI size row."""
    ws = _S["ws"]
    _ZOOM[0] = int(zoom)
    ws.look.zoom_glass(int(zoom), tuple(int(z) for z in zooms))
    ws.resize_glass(int(w), int(h), glass_in(int(w), int(h)))


def glass_in(w, h):
    """The diagonal a `w` x `h` page glass declares: where it holds the
    desk's room (`layout_base.desk_room`), the P4's glass at the P4's pixel
    density (`layout_base.desk_diagonal_in`), so it lays out on the desk's
    metrics and tap floor as that board does at any page size; below it
    none, as the T-Deck declares none, so a phone and a small window lay
    out the handheld at its chrome scale."""
    if layout_base.desk_room(w, h, 1):
        return layout_base.desk_diagonal_in(w, h)
    return None


# This frame's samples, as step_frame_json leaves them for the worker: their
# count (0: none), the first's index in the stream, 1 where they start one,
# and the heap address they wait at (_RunnerPump._buf). 64-bit integers, so a
# count of samples past 2**31 reads true and none passes through the VM's
# single-precision float.
_PCM = array("q", (0, 0, 0, 0))


def pcm_addr():
    """Where `_PCM` lives in the heap, for the worker to read each frame."""
    import uctypes
    return uctypes.addressof(_PCM)


def _pcm_buf(au):
    a = _S.get("pcm_buf")
    if a is None:
        import uctypes
        a = _S["pcm_buf"] = uctypes.addressof(au._buf)
    return a


def _wifi_panel(ws):
    """The Wi-Fi panel as a harness drives it: the networks listed, the
    saved ones, its line, the focused stop, whether a join runs, and the
    console's question or card over it (its verb and title)."""
    sl = getattr(ws, "settings_layer", None)
    if sl is None:
        return None
    c = ws.confirm
    return {"nets": [n[0] for n in sl.wifi_nets], "known": list(sl.wifi_known),
            "msg": sl.wifi_msg, "focus": sl._sub_focused, "pick": sl.wifi_pick,
            "joining": sl.wifi_joining is not None,
            "card": [c.verb, c.title] if c.open else None}


def _edit_state(ws):
    """What a key in the Editor changed, for a harness that types into it:
    the open tab, the sprite's pixels as hex, the code's first lines and
    whether it holds a selection, and whether the system menu shows, with
    its rows' words (`menu`) and the highlighted one's place among them
    (`menu_at`)."""
    m = ws.sysmenu
    out = {"tab": getattr(ws, "menu_view", None),
           "sysmenu": bool(getattr(m, "open", False))}
    if out["sysmenu"]:
        rows = [r for r in m.items if r[0] == "item"]
        out["menu"] = [r[4] if len(r) > 4 else str(r[1]) for r in rows]
        out["menu_at"] = sum(1 for r in m.items[:m.sel] if r[0] == "item")
    pe, sheet = getattr(ws, "paint", None), getattr(ws, "sheet", None)
    if pe is not None and sheet is not None:
        ox, oy = sheet.tile_origin(pe.n)
        out["sprite"] = "".join("%x" % sheet.pget(ox + x, oy + y)
                                for y in range(pe.dim) for x in range(pe.dim))
        out["tool"] = pe.tool
    ed = getattr(ws, "editor", None)
    if ed is not None:
        out["code"] = ed.lines[:4]
        out["sel"] = bool(ed.has_selection())
        out["selected"] = ed.selected_text()[:60] if ed.has_selection() else ""
        out["top"] = ed.top
        out["caret"] = [ed.row, ed.col]
        page = getattr(ws.code_layer, "page", None) if out["tab"] == "code" else None
        view = page.views.get("code") if page is not None else None
        if view is not None:
            out["autoscroll"] = ws.code_layer.autoscrolling()
            # where the text lies on the glass: x of column 0, y of the top
            # row, a cell, a line, as the page last drew its text view. On
            # the desk the page draws in its pane's body (EditorDesk.laid_out),
            # the pane in the Editor window's content.
            rect, _top, cell, lh, x0 = view[:5]
            ox = oy = 0
            desk = getattr(ws, "built_editor_desk", None)
            got = desk.laid_out("code") if desk is not None else None
            if got is not None:
                ox, oy = got[0][:2]
                win = getattr(getattr(ws, "wm", None), "windows", {}).get("menu")
                if win is not None:
                    cx, cy = win.content_rect()[:2]
                    ox, oy = ox + cx, oy + cy
            out["grid"] = [ox + x0, oy + rect[1], cell, lh]
    return out


def _input_state(ws):
    """Which input the console follows, for a harness that drives it with a
    gamepad: the input in use and the one the hints draw the keys of
    (`ui_draw.INPUTS`), the sources declared, the desk's focused tile, the
    home's tab and selected card, and the pause card's rows and the one
    focused while it is up."""
    import ui_draw
    p = ws.pause
    desk = getattr(ws.wm, "desk_focus", None)
    return {"desk_focus": desk() if desk is not None else None,
            "kind": ui_draw.input_kind(), "hints": ui_draw.hint_kind(),
            "sources": sorted(ws.input_kinds or ()),
            "home_sel": getattr(ws.launcher, "sel", None),
            "home_tab": getattr(ws.launcher, "tab", None),
            "pause": list(p.rows) if p.open else None, "pause_sel": p.focused()}


def state_json():
    """The console's `state`: the dev channel's one-line snapshot -- the keys
    every on-glass suite reads -- plus this page's sample stream
    (`moy_audio.snd_counts()`: frames a compiled cart queued, frames the page's
    audio pull mixed, frames it found none, the room, whether it is open, its
    depth), the page's pull (`pcm`: its rate, the samples it sent the
    page's sink and the sink's count of those it played), and
    the running cart's first 32 pmem slots, the earned badges' ids, the
    Settings rows as the console holds them, whether the FPS chip shows and
    the store's sync (`sync`: the batches its far end has taken, and whether
    one is on its way), the Terminal's grid as lines (`term`, None before
    it first opens), the media stream's `now()` (`media`, None with no run)
    and how its last run ended (`media_last`, dev_media.last), the heap's
    allocation where the page meters it (`alloc`, step_frame_json's), the
    buttons held (`held`), the page's word (`page`: full screen, where it
    keeps the carts, whether a console serves it, whether its browser has
    full screen, whether it runs as a home-screen app, its host), the card
    up (`card`: its verb, title and lines; None), the notice up
    (`notice_up`: title, sub, kind; None), the glass's metric class,
    chrome scale, top bar thickness in glass pixels and the back-stack's
    floor and depth (`glass`), the desk keyboard's
    typing level (`typing`), and the radio link's stats (`link_stats`, EspNowLink.stats: the match's
    frame, checkpoints and desync; None with no link), the relayed devices'
    channel (`devs`, `_live_devs`), for a harness
    driving the page (`window.__moyState()`), and the Wi-Fi panel's
    (`wifi_panel`, `_wifi_panel`)."""
    import dev_channel
    st = dev_channel._remote_state(_S["ws"])
    st["ach"] = sorted(_S["ws"].ach.doc().get("system", {}).get("found", {}))
    st["system"] = json.loads(_S["ws"].system.dump() or "{}")
    st["show_fps"] = bool(_S["ws"].show_fps)
    inp = _S["ws"].input
    st["held"] = [n for n in web_input.BUTTON_NAMES if inp.held(n)]
    st["typing"] = inp.source("local").typing
    st["sync"] = {"acked": _S.get("sync_acked", 0),
                  "busy": any(w.busy() for w in _watchers())}
    st["edit"] = _edit_state(_S["ws"])
    pg = _S["ws"].page
    st["page"] = None if pg is None else {"fs": pg.fullscreen, "kept": pg.kept,
                                          "served": pg.served, "canfs": pg.can_fullscreen,
                                          "app": pg.app, "host": pg.host}
    cf = _S["ws"].confirm
    st["card"] = {"verb": cf.verb, "title": cf.title,
                  "lines": [t for t, _tone in cf.line_rows()]} if cf.open else None
    st["input"] = _input_state(_S["ws"])
    st["wifi_panel"] = _wifi_panel(_S["ws"])
    ws = _S["ws"]
    st["notice_up"] = (list(ws.notice_up) if ws.notice_up is not None
                       and ws.notices.notice_active() else None)
    st["glass"] = {"cls": ws.metric_class, "cs": ws.look.effective_chrome_scale(),
                   "bar": ws.layout.status_h * ws.render_scale,
                   "floor": ws.wm.floor(), "depth": ws.wm.stack.depth()}
    term = getattr(_S["ws"].app("terminal"), "face", None)
    st["term"] = term.lines() if term is not None else None
    try:
        import moy_audio
        sc = moy_audio.snd_counts()
    except (ImportError, AttributeError):
        sc = None
    st["snd"] = list(sc) if sc is not None else None
    au = getattr(_S["ws"], "audio_out", None)
    st["pcm"] = {"rate": au.rate, "sent": au.sent, "played": au.played} \
        if hasattr(au, "sent") else None
    st["alloc"] = dict(_ALLOC) if _METER[0] else None
    try:
        import dev_media
        st["media"] = dev_media.now()
        st["media_last"] = dev_media.last()
    except ImportError:
        st["media"] = st["media_last"] = None
    # The running cart's first pmem slots, where a fixture reports its checks:
    # the run's flush, which hands a moved image to the console's pmem for the
    # frame's pmem save (Player._pmem_tick) to keep, then its image.
    run = getattr(_S["ws"].run.player, "lua", None)
    flush = getattr(run, "flush_pmem", None)
    if flush is not None:
        flush()
    img = getattr(run, "pmem_img", None)
    st["pmem"] = list(img)[:32] if img is not None else None
    lk = getattr(_S["ws"], "link", None)
    st["link_stats"] = lk.stats() if lk is not None else None
    st["devs"] = _live_devs()
    g = _S.get("gpio")
    st["gpio"] = {"live": g.live, "rt": g.rt} if g is not None else None
    return json.dumps(st)


def _live_devs():
    """The live socket's device channel on this page (moy_dev_web.c's
    counts), None where its board relays no kind."""
    import devices
    if not devices.RELAYED:
        return None
    import moy_net
    v = moy_net.live_devs()
    return dict(zip(("kinds", "rows", "opens", "up", "down", "records", "events", "dropped",
                     "timed", "rtt_min_us", "rtt_max_us", "rtt_sum_us", "rtt_last_us"), v))


def _apply(events):
    d = _S["driver"]
    web_input.apply_events(
        events, d.input, _S["sink"],
        on_press=d.press, on_pan=d.pan, on_key=d.type_char,
        on_esc=d.escape, on_hold=d.hold, on_key_hold=d.key_hold,
        on_super=d.system_key, on_full=d.full_key, on_key_down=d.key_down,
        on_key_up=d.key_up, on_mods=d.set_mods, on_wheel=d.wheel, on_middle=d.middle,
        on_gamepad=_gamepad, on_paste=_paste, on_glass=glass,
        on_page=lambda ev: _S["ws"].page.heard(_S["ws"], ev))


# The console's clipboard as the page last heard of it: its seq (moy_app.h's
# clip_seq) at the last copy the page was sent, or the last paste it sent.
_CLIP = [None]


def _paste(text):
    """The page's clipboard pasted: the console takes it
    (`ConsoleDriver.paste`), and the page's clipboard holds it already."""
    _S["driver"].paste(text)
    _CLIP[0] = _S["ws"].clipboard.seq()


def _clip_out():
    """The console's clipboard's text where a copy changed it since the
    page last heard (None where none did): the page puts it on the
    browser's clipboard."""
    clip = _S["ws"].clipboard
    seq = clip.seq()
    if seq == _CLIP[0]:
        return None
    first = _CLIP[0] is None
    _CLIP[0] = seq
    if first or clip.kind() != "text":
        return None
    return clip.text()


def _gamepad(on):
    """A gamepad held at the page connected (`on`), or the last one left:
    its source joins the console's inputs as the `pad` kind, the input in use
    from then on so the focus and the pad's keys show at once, and leaves
    them with nothing held."""
    ws = _S["ws"]
    if on:
        ws.input_joined(web_input.GAMEPAD_SOURCE, "pad")
    else:
        ws.input_left(web_input.GAMEPAD_SOURCE)


def store_mode(mode=None, seeded=None):
    """Which world this page is in, told to us by the worker BEFORE boot().

    The worker decides it (moy_store.probeMode) before anything is written,
    because the answer is what the VFS gets seeded FROM. boot() then needs it
    for one decision only: whether the carts watcher sweeps the journal, which
    it does exactly when THIS browser is the store of record ("site"). So this
    must be called before boot() -- after it, the watcher already exists and a
    late mode would be a setting with no effect, which is the shape of bug this
    whole file is careful about.

    Anything other than "site" ("board", "none", or never called at all) leaves
    the wire's own predicate in place. That default matters more than the
    setting: a mode that fails to arrive must not start shipping journals at a
    board.

    `seeded` is the ids of the roots the worker seeded (None: unknown, every
    present root): a board-mode page watches only what its board served.
    """
    _S["store_mode"] = mode or None
    _S["seeded"] = None if seeded is None else tuple(seeded)
    return ""


def site_sources(carts_root, doc_json):
    """The shelves whoever serves a site-mode page chose, its indexes.json:
    `indexes`, [url, ...], as the console's `system/sources`
    (cart_index.save_sources), a board's twin; and `own`, the release index
    whose official carts the page lists (`ws.cart_own`: site/build.py names
    its channel's release on os.moybyte.com). Each is optional. The index
    at `own` lists official carts only when its signature verifies under
    the release keys the bundle bakes in (`_cart_seams`), so a host that
    names another index gets no official cart for it. A page a board serves
    browses the board's own, and a page with no indexes.json the console's
    default shelves and no release. Called after `store_mode` and before
    `boot`."""
    if _S.get("store_mode") == "board":
        return ""
    try:
        doc = json.loads(doc_json)
    except ValueError:
        return ""
    if not isinstance(doc, dict):
        return ""
    import cart_index
    own = doc.get("own")
    if cart_index.is_url(own):
        _S["cart_own"] = own
    urls = doc.get("indexes")
    if isinstance(urls, list):
        cart_index.save_sources(carts_root, [u for u in urls if isinstance(u, str)])
    return ""


def sync_poll_json():
    """One sweep + the next wire batch as JSON, or "" (nothing changed, or a
    batch is already awaiting its answer). The worker calls this about once a
    second -- the sweep is a stat walk of an in-memory VFS, so its cost is
    noise; the READ of changed files happens only when something committed.

    ONE BATCH IN FLIGHT is a rule about the TRANSPORT, so it is enforced here
    across both roots rather than left to each watcher's own `take`. The worker
    posts one body at a time and acks before polling again -- but a poll that
    fell through to the files root while a carts batch was still unanswered
    would hand out a second body on that promise, and `sync_ack` would then
    settle the wrong one."""
    live = _watchers()
    for w in live:
        if w.busy():
            return ""
    for w in live:
        w.sweep()
        body = w.take_json()
        if body:
            _S["sync_took"] = w.root_id
            return body
    return ""


def sync_root():
    """The root id of the batch `sync_poll_json` last handed out: the store a
    site-mode page applies it into."""
    import moy_sync
    return _S.get("sync_took") or moy_sync.CARTS_ROOT_ID


def sync_ack(ok):
    """Settle the in-flight batch: the worker's POST got an answer (ok=True
    clears it; anything else requeues every path it carried). Routed to the
    watcher that TOOK it -- acking the wrong root would strand its batch in
    flight forever and requeue nothing."""
    import moy_sync
    watchers = _S.get("watchers") or {}
    w = watchers.get(_S.get("sync_took") or moy_sync.CARTS_ROOT_ID)
    if w is not None:
        w.ack(bool(ok))
    if ok:
        _S["sync_acked"] = _S.get("sync_acked", 0) + 1
    return ""


def sync_off():
    """The far end has no /sync at all (a static host, an old read-only board):
    stop sweeping for good. One failed probe, then silence -- the standalone
    browser console must not retry-log forever.

    EVERY root, because this is the "there is no push half here" answer. A board
    that has /sync but no files layer is a different case entirely, and it is
    settled at boot: no files store in the VFS means no files watcher, so
    nothing ever probes for a files endpoint that would 404."""
    _S["watchers"] = {}
    return ""


def gpio_enable(pins_json):
    """The host answered the /gpio probe: wire the pin verbs (#9).

    Called by the worker in the boot script, so this lands BEFORE any cart can
    start and the availability question is settled exactly once. A host that
    did not answer never calls it, and `pin_write`/`pin_read` then have no name
    at all -- the repo's standing rule for a capability that is not there.

    `pins_json` is the allowlist the board sent. Kept rather than assumed,
    because the refusal has to be able to say WHICH pins this board has, and
    the browser cannot know that: the answer is a fact about the hardware on
    the other end of the wire.
    """
    try:
        pins = json.loads(pins_json)
    except Exception:                # noqa: BLE001 -- a garbled probe answer
        pins = None
    if not pins:
        return ""
    try:
        from gpio_link import GpioLink
        _S["gpio"] = GpioLink(pins)
    except Exception as exc:         # noqa: BLE001 -- never block a boot
        print("gpio unavailable:", exc)
    return ""


def services_json():
    """Which capability seams this console ACTUALLY has, as JSON.

    Written because the observable lied. The worker posted `{t:"update"}` on the
    strength of the PROBE having answered and its own comment called that "did
    the bridge bind?" -- so a page could report an updater while the console
    behind it had none, and a browser test asserting on that message proved the
    probe and nothing else. A seam is live or it is not, and only the console
    can say which.

    Cheap and read-only: four getattrs, called once after boot and by a harness
    that wants to know. It is the browser tier's answer to the question
    tests/test_board_service_parity.py asks of every other tier by reading
    source -- here the wiring is decided at RUNTIME, by what the far end
    answered, so no amount of source-reading can settle it.
    """
    ws = _S.get("ws")
    if ws is None:
        return "{}"
    return json.dumps({
        "updater": getattr(ws, "updater", None) is not None,
        "wifi": getattr(ws, "wifi", None) is not None,
        "gpio": getattr(ws, "gpio", None) is not None,
        "net": getattr(ws, "net", None) is not None,
        "can_manage": bool(getattr(ws, "can_manage", False)),
        "cart_net": getattr(ws, "cart_net", None) is not None,
        "cart_keep": getattr(ws, "cart_keep", None) is not None,
        "cart_home": getattr(ws, "cart_home", None),
        "cart_board": getattr(ws, "cart_board", None) is not None,
    })


def update_enable(status_json):
    """The host answered the /update probe: give the console an UPDATER (#41).

    Same shape and same moment as `gpio_enable`, and for the same reason -- the
    availability question is a fact about the far end, settled once, before any
    screen can ask. A host that did not answer never calls this, `ws.updater`
    stays None, and Settings simply has no update row: the standing rule for a
    capability that is not there, rather than a row that fails when tapped.

    What this buys is the whole point of doing it here instead of in the page:
    `runtime/system/update_ui.py` is 659 lines that are ALREADY frozen into this
    bundle, and were dead only because nothing was injected. The console gets
    the same update screen every board shows, reached from the same Settings
    row, with the same two-act confirm -- rather than a second update UI drawn
    in page chrome.
    """
    try:
        doc = json.loads(status_json)
    except Exception:                # noqa: BLE001 -- a garbled probe answer
        return ""
    if not isinstance(doc, dict) or "running" not in doc:
        return ""
    try:
        from update_link import RemoteUpdater
        _S["update"] = RemoteUpdater(doc)
        _S["ws"].updater = _S["update"]
    except Exception as exc:         # noqa: BLE001 -- never block a boot
        print("update unavailable:", exc)
    if _S["ws"].cart_home is not None and not doc.get("screen"):
        _S["ws"].cart_home = "headless"
    return ""


def wifi_enable(doc_json):
    """The serving board answered the /wifi probe: its Wi-Fi is the
    console's (wifi_link.BoardWifi). Before `boot`, which wires it as the
    console's station, so the bar lays its glyph out from the first frame."""
    try:
        doc = json.loads(doc_json)
    except Exception:                # noqa: BLE001 -- a garbled probe answer
        return ""
    if not isinstance(doc, dict) or "connected" not in doc:
        return ""
    try:
        from wifi_link import BoardWifi
        _S["wifi"] = BoardWifi(doc)
    except Exception as exc:         # noqa: BLE001 -- never block a boot
        print("wifi unavailable:", exc)
    return ""


def wifi_poll_json():
    """The next request for the worker to POST to /wifi, or ""."""
    w = _S.get("wifi")
    return w.take_json() if w is not None else ""


def wifi_wants_poll():
    """True when the worker should GET /wifi now."""
    w = _S.get("wifi")
    return bool(w is not None and w.wants_poll())


def wifi_ack_json(ok, text=""):
    """Settle the request or poll in flight with the board's document;
    what the worker must know back (BoardWifi.ack), or ""."""
    w = _S.get("wifi")
    if w is None:
        return ""
    out = w.ack(bool(ok), text or "")
    _S["ws"].mark_dirty()
    return out


def wifi_moved(ssid):
    """The worker waited out a move the board never came back from: it is
    on `ssid` (BoardWifi.moved)."""
    w = _S.get("wifi")
    if w is not None:
        w.moved(str(ssid))
        _S["ws"].mark_dirty()
    return ""


def official_enable():
    """The serving console answered the /official probe: it installs
    carts when this page asks. Called before
    `boot`, which hands Get Carts the asking (`_cart_seams`), so the app
    never opens on a page that says the console gets its own."""
    _S["official"] = True
    return ""


def update_poll_json():
    """The next queued request, or "" -- the worker POSTs it to /update. When
    there is nothing to send it answers "" and `update_wants_poll` decides
    whether to GET instead."""
    u = _S.get("update")
    return u.take_json() if u is not None else ""


def update_wants_poll():
    """True when the screen is waiting on something and no request is in
    flight, so the worker should GET the status. Polling only while a screen
    cares is what keeps an idle console off the wire entirely."""
    u = _S.get("update")
    return bool(u is not None and u.wants_poll())


def update_ack_json(ok, text=""):
    """Settle the in-flight request or poll: `text` is the board's status
    document, which is where every number the screen prints comes from."""
    u = _S.get("update")
    if u is not None:
        u.ack(bool(ok), text or "")
    return ""


def update_off():
    """The far end stopped answering. The updater STAYS (a screen may still be
    open) and goes inert reporting an error -- see RemoteUpdater.stop."""
    u = _S.get("update")
    if u is not None:
        u.stop()
    return ""


def gpio_poll_json():
    """The next batch of queued pin ops, or "" -- the worker POSTs it to the
    relative /gpio of whoever served the page, exactly like the sync push."""
    g = _S.get("gpio")
    return g.take_json() if g is not None else ""


def gpio_ack_json(ok, text=""):
    """Settle the in-flight batch: `text` is the board's answer, whose `reads`
    are what `pin_read` returns until the next one arrives."""
    g = _S.get("gpio")
    if g is not None:
        g.ack(bool(ok), text or "")
    return ""


def gpio_off():
    """The far end stopped answering /gpio. The verbs STAY (a running cart is
    holding them) and go inert -- see GpioLink.stop."""
    g = _S.get("gpio")
    if g is not None:
        g.stop()
    _S["gpio"] = None
    return ""


# -- the Terminal's link to the serving board's shell --------------------------------
#
# The Terminal's face on the bundle a board bakes is a face of that board's
# shell (native/moy_sh/moy_sh_link.h): its `remote` app's grid is the board's
# bytes and its keys go back. The worker owns the socket (GET /term on the
# board, native/moy_tty's bridge) and moves what these hand it, between
# frames; nothing here waits on the network.

_TERM_NONE = 9                          # MOY_SH_LINK_NONE


def _link():
    """The C face's link ends, or None (the site's console runs its own shell)."""
    try:
        import moy_sh
    except ImportError:
        return None
    return moy_sh if hasattr(moy_sh, "link_want") else None


def term_enable(on):
    """Whether this page has a board's shell to reach: a board-served page
    does; any other says so in the Terminal and never asks."""
    sh = _link()
    _S["term"] = bool(on) and sh is not None
    _S["term_rest"] = b""
    if sh is not None and not on:
        sh.link_state(_TERM_NONE, 0)
    return ""


def term_poll_json():
    """What the Terminal asks of the socket since the last poll, or "":
    {"want": 1 (open) | 2 (close), "cols", "rows", "size": [c, r], "out": [byte, ...]}.
    The bytes the board sent that the grid had no room for go in first."""
    sh = _link() if _S.get("term") else None
    if sh is None:
        return ""
    rest = _S.get("term_rest")
    if rest:
        _S["term_rest"] = rest[sh.link_in(rest):]
    want, cols, rows, sized = sh.link_want()
    out = sh.link_out()
    if not (want or sized or out):
        return ""
    d = {}
    if want:
        d["want"] = want
        d["cols"] = cols
        d["rows"] = rows
    if sized:
        d["size"] = [cols, rows]
    if out:
        d["out"] = list(out)
    return json.dumps(d)


def term_feed(b64):
    """The board's bytes (base64, as the worker carries them) into the grid."""
    sh = _link() if _S.get("term") else None
    if sh is None:
        return ""
    import binascii
    data = _S.get("term_rest", b"") + binascii.a2b_base64(b64)
    _S["term_rest"] = data[sh.link_in(data):]
    return ""


def term_state(state, n=0):
    """What became of the socket (MOY_SH_LINK_*), said in the Terminal."""
    sh = _link() if _S.get("term") else None
    if sh is not None:
        _S["term_rest"] = b""
        sh.link_state(int(state), int(n))
    return ""


# -- the live socket: the radio link and the relayed devices -----------------------
#
# A page served by a board that relays a device kind (GET /live's "kinds")
# holds its handles as remote rows (live_kinds), their calls and the board's
# pushes moved by the same feed and pump as the link's.
#
# A page served by a board that relays its radio (a Zero: GET /live answers
# {"link":1}, native/moy_net/moy_live.c) has a link as a console board does:
# `ws.link` is players.EspNowLink over the kernel's Match, whose radio is the
# page's half of the link channel (native/moy_net/moy_link_web.c), so a
# match here is a console's match, its inputs riding the socket to the board
# and its radio. The worker owns the socket: what the board sent goes into
# the link before each frame (live_feed), so the frame's match finds it, and
# after the frame live_pump runs the link's poll (its beacon, a START or a
# BYE) and hands back what it queued. Nothing here waits on the socket.

_LIVE_GAP_MS = 250                      # a frame gap a live match says it waited through


class _LiveWlan:
    """The station `EspNowLink` reads, which is the page's board's: its MAC
    (the /live probe's) is the page's address on the air, and its channel
    pinned (the 'H' state; 0 before the socket first opens)."""

    def __init__(self, mac):
        self.mac = mac

    def active(self, on=None):
        return True

    def isconnected(self):
        return True

    def config(self, *a, **kw):
        if kw or not a:
            return None
        if a[0] == "mac":
            return self.mac
        if a[0] == "channel":
            import moy_net
            return abs(moy_net.live_info()[5])
        return 0


def live_hints(on):
    """Whether the board's live socket is open and says when its routes'
    answers change (native/moy_net/moy_live.c, THE HINTS): Get Carts' board
    requests ask on its hint rather than on their clock."""
    import carts_link
    carts_link.pushed(on)
    return ""


def official_hint():
    """The board said its /official answer changed."""
    import carts_link
    carts_link.hint()
    return ""


def store_pulled():
    """The worker brought the served store over the VFS because the board
    said it changed (its hint 's': an SSH session's edit, another page's
    sync): the shelf reads it again and every watcher adopts it
    as its baseline, as a reload does, with no cart restarted."""
    _rescan()
    for w in _watchers():
        w.rebase()
    return True


def live_kinds(spec):
    """The board relays device kinds on the live socket (the /live probe's
    "kinds", native/moy_kernel/moy_dev_kinds.h's THE RELAY): their handles
    become the kernel table's remote rows here (native/moy_net/
    moy_dev_web.c), and the console has the device APIs they name
    (devices.RELAYED), as a console board with the device has."""
    try:
        import moy_net
        import devices
        if not hasattr(moy_net, "live_kinds"):
            return ""
        # "pins" is the pin verbs' (gpio_link.py, THE PINS), not a device API
        kinds = [k for k in spec.split(";") if k]
        _S["pins_live"] = "pins" in kinds
        kinds = [k for k in kinds if k != "pins"]
        moy_net.live_kinds(";".join(kinds))
        devices.RELAYED = tuple(k.split(":")[0] for k in kinds)
    except Exception as exc:         # noqa: BLE001 -- never block a boot
        print("live kinds unavailable:", exc)
    return ""


def live_enable(mac):
    """The board answered the /live probe: the socket is this page's. Where
    it relays its radio, with its address (`mac`, hex; "" where not), the
    console gains a link, as a console board wires one
    (device/wire_links.py), before the address's cart starts."""
    ws = _S.get("ws")
    if ws is None:
        return ""
    try:
        import binascii
        import moy_net
        if not hasattr(moy_net, "live_take"):
            return ""
        if mac:
            from players import EspNowLink, launch_cart
            ws.link = EspNowLink(board="web", name="Browser",
                                 wlan=_LiveWlan(binascii.unhexlify(mac)), launch=launch_cart)
            ws.net = ws.link.net
        _S["live"] = {"open": False, "said": None, "hidden": False, "gap": False,
                      "check": _S.get("linkcheck", False)}
    except Exception as exc:         # noqa: BLE001 -- never block a boot
        print("live link unavailable:", exc)
    return ""


def _live_say(ws, key):
    notice = getattr(getattr(ws, "notices", None), "notice", None)
    if notice is None:
        return
    try:
        import ui_draw as _ud
        notice(_ud.s("notice." + key), _ud.s("notice." + key + "_why"), "warn")
    except Exception as exc:         # noqa: BLE001 -- a notice must never kill a frame
        print("live notice failed:", exc)


def live_state(open_, why=""):
    """The socket opened (1) or closed (0). A drop while the radio is held
    is said on the screen, and so is its return: the match waits meanwhile,
    as it does for a lost input."""
    st = _S.get("live")
    ws = _S.get("ws")
    if st is None or ws is None:
        return ""
    import moy_net
    on = bool(int(open_))
    moy_net.live_open(on)
    held = moy_net.live_info()[1]
    if on != st["open"]:
        print("[live] socket %s%s" % ("open" if on else "closed", (": " + why) if why else ""))
        if held:
            _live_say(ws, "link_back" if on else "link_lost")
    st["open"] = on
    g = _S.get("gpio")
    if g is not None:
        g.live_open(on and _S.get("pins_live", False))
    return ""


def live_feed(b64):
    """Plaintexts of the link and device channels the board sent, each
    behind its 2-byte length, base64 as the worker carries them, into the
    link, but the pins row's, which are the pin verbs' (gpio_link.py)."""
    if _S.get("live") is None:
        return ""
    import binascii
    import moy_net
    data = binascii.a2b_base64(b64)
    g = _S.get("gpio")
    at = 0
    while at + 2 <= len(data):
        n = data[at] | data[at + 1] << 8
        pl = data[at + 2:at + 2 + n]
        if g is not None and n >= 3 and pl[0] == 0x64 and pl[2] == g.ROW:
            g.live_in(pl)
        else:
            moy_net.live_give(pl)
        at += 2 + n
    return ""


def live_pump(gap_ms=0, hidden=0):
    """Between frames: the link's poll, then what it and the pin verbs
    queued for the board, base64 (each plaintext behind its length), or "". `gap_ms` is the time
    since the frame before, `hidden` whether the page's tab is hidden: a
    live match that waited through a gap says so once it moves again."""
    st = _S.get("live")
    ws = _S.get("ws")
    if st is None or ws is None:
        return ""
    lk = getattr(ws, "link", None)
    if lk is not None:
        lk.poll()
        if st["check"] and lk.active:
            lk.check_worlds(True)
            st["check"] = False
    if getattr(ws, "netplay", None) is not None:
        if int(hidden):
            st["hidden"] = True
        if int(gap_ms) > _LIVE_GAP_MS and st["hidden"]:
            st["gap"] = True
        if st["gap"] and not int(hidden):
            st["gap"] = st["hidden"] = False
            _live_say(ws, "match_waited")
    else:
        st["gap"] = st["hidden"] = False
    import moy_net
    out = moy_net.live_take() or b""
    g = _S.get("gpio")
    if g is not None:
        for pl in g.take_live():
            out += bytes([len(pl) & 255, len(pl) >> 8]) + pl
    if not out:
        return ""
    import binascii
    return binascii.b2a_base64(out).decode().strip()


def idle_collect():
    """Run the deferred split-heap collect NOW -- called by the worker on a
    quiet streak, so the full mark+sweep lands on an idle frame instead of
    mid-gesture. Under GC_SPLIT_HEAP_AUTO
    gc.collect() only sets the pending flag; the real collect executes when
    THIS call returns to JS (the top level) -- exactly the boundary we chose."""
    import gc
    gc.collect()
    return ""


def apply_events_json(text):
    """Queue a browser {"events":[...]} JSON text batch for the next frame,
    which feeds it through the ONE shared decode path (the same wire format
    the WS transports speak)."""
    web_input.apply_ws_text(text, _S.setdefault("evq", []).extend)


def _feed_events():
    """One frame's share of the queued events, in order: all of them, or as
    many as keep each change of the pointer its own frame; the next frame
    takes the rest (`web_input.frame_cut`)."""
    q = _S.get("evq")
    if not q:
        return
    n = web_input.frame_cut(q)
    if n == len(q):
        _S["evq"] = []
        _apply(q)
    else:
        _S["evq"] = q[n:]
        _apply(q[:n])
