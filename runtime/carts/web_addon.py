# Map (grep -n a name to jump there):
#   installed              the add-on folders (web_console_<12 hex>.moy) a carts root holds
#   AddonStep              the add-on that fits this image, and on the XIAO Zero the official carts, brought to it
#   official_behind        the official carts a store holds that its release has newer
#   OfficialCarts          /official's backend: the carts of its shelves a page asks a headless board for
"""The browser console add-on: a cart, one per page (tools/web_pack.py makes
them), whose pack the webhost serves (native/moy_net/moy_page.h); and on a
Zero the official carts, which its release publishes in the same index.

The firmware names the page it serves (moy_web.page_want), and its release
publishes, beside its manifest, a signed index listing the add-ons it
published, newest first (on the beta those of the last 30 days, within the
index's budget: tools/web_pack.py), each naming the page it fits
(`moybyte.fits`). Every board gets
the one that fits it through the ordinary install (cart_index.Install: every
file checked against the signed index before the folder moves into place):
from Get Carts like any cart, or by this module's step (`AddonStep`). The
website's install writes it into the store with the image
(tools/store_image.py).

AFTER A FIRMWARE UPDATE the add-on that was installed fits the old image, so
the webhost answers "needs its page updated" until the one that fits the new
image is installed. `AddonStep` does that: started once the new image has
confirmed itself (so an image the bootloader rolls back never replaced the
add-on its predecessor serves), and on every boot whose add-on does not fit,
which is how an install a reset cut short resumes. It reads the console's own
index, installs the entry that fits, and takes the add-on folders that no
longer fit off the shelf. A step is one frame's share (`tick`); the radio is
the caller's lease (`inst.hold`/`release`).

WHERE THE ONE THAT FITS IS THERE ALREADY (the website's install, a cable
push, moy_seed.bring_addon's move to a card) the others are taken off at the
confirm all the same (`tidy`, once a boot, before the step's start): the
folders as the shelf lists them, or as the carts folder does where the board
keeps no shelf (a Zero), so a console's warm boot lists nothing more. That is
housekeeping, not an owner's removal: it writes no line to `system/removed`.

WITH `absent` (every board) a store with NO add-on gets the one that fits
too, unless its owner removed the console: a removal records it
(moy_seed.ADDON_LINE in `system/removed`, which Get Carts' install of it
drops again), and a board with that line never fetches it. A board the
website's flasher wrote carries the add-on in its store already; the step
brings it to a wiped store, a cable flash whose add-on step failed, and a
console that had none before. On a console it waits for a network: it does
nothing at all where none is saved (`inst.configured()`), never runs while a
game plays (`inst.playing()`: a start is put off and a running step stops,
the shelf as it was), and a failed attempt is tried again after RETRY_MS,
doubling to RETRY_MAX_MS (`due`, which the console's frame polls; a Zero's
serving loop asks again itself). A boot's confirm starts it, a WiFi join
(`nudge`) and the update screen's exit start it again.

A STORE TOO SMALL FOR THE ADD-ON is found out once, and not a failure: the
index names the pack's size, and where it does not fit the store's free space
(`inst.free()`, the cart index's `need_bytes` and `room_why`) the step records
the page digest and the bytes it needs in `system/addon_room`, lets the radio
go and ends with no back-off. From then on `short` answers it before anything
else: a boot's or a join's start holds no radio, fetches no index and waits for
the free space to reach the record, which a mounted card or deleted carts do
(`short` reads the space again when the screen opens, on a person's press and
every few seconds while the screen asks). The console's screen says what the
add-on needs (`short_text`) and offers no Update meanwhile.

WITH `carts` (the XIAO Zero, which updates over the air) the same step
brings the OFFICIAL carts the store holds to the release: every official
entry of the index (cart_index.parse_index, the console's own index with its
signature verified) whose cart the store holds at an older manifest version
-- the seed's own rule (#47) -- is installed over it through the same
Install, a cart at a time, its saves and an edited config carried; an
unchanged cart is not fetched at all. The carts its image carries are
current already (the new image's seed, zero_host.seed_carts, runs before
the step), so what it fetches is the official carts the page installed. The
release it brought them to is the stamp `system/official` beside the carts
folder (the page digest the image names), so a cut one resumes and a store
already there asks nothing. A console board's image carries every seed cart
and seeds them itself, so its step is the add-on's alone.

A BOARD'S PAGE asks for the rest (`OfficialCarts`, the webhost's sealed
`/official`, on a Zero and a console with glass alike): the browser console
it serves lists the carts of the indexes the board reads (its
`system/sources`, else moybyte-org/carts, and its own release's) and asks
the board to install or remove one, and the board
fetches over its own network and writes its own store -- the board stays
the one writer of its carts, as with `/update`.

`inst` is the install role's server as the shell drives it
(runtime/shell/shell_servers.py's InstallServer, bound), or the Zero's
stand-in: `net()`, `root()`, `op(fn)` (one store op), `chip()`, `hold()`,
`release()` and `rescan(folder)`. `index` is the console's own index url, or
a callable answering it.
"""

import json

import cart_index as _ci
from moy_fs import _exists, _read, _write_atomic, _mkdir
from moy_seed import ADDON_LINE as _ADDON_LINE, addon_removed as _addon_removed, \
    unremove as _unremove
from moy_store_base import _sibling_path, cart_path as _cart_path

PREFIX = "web_console_"         # tools/web_pack.py's CART_ID, then 12 hex, then .moy
STATE_ABSENT = 1                # moy_page.h's MOY_PAGE_ABSENT
STATE_STALE = 2                 # moy_page.h's MOY_PAGE_STALE
STATE_READY = 3                 # moy_page.h's MOY_PAGE_READY
STEP_MS = 8                     # an install's work in one frame
RETRY_MS = 60000                # a failed attempt starts again no sooner
RETRY_MAX_MS = 3600000          # and each failure doubles the wait, up to this


def installed(root, op):
    """The add-on folders under `root`, whichever page each fits."""
    def _list():
        import os
        try:
            return sorted(n for n in os.listdir(root)
                          if n.startswith(PREFIX) and n.endswith(".moy"))
        except OSError:
            return []
    return op(_list)


def page_state():
    """moy_page.h's state of this console's page, or None where there is no
    webhost (the host's console, a browser)."""
    try:
        import moy_net
    except ImportError:
        return None
    state = getattr(moy_net, "page_state", None)
    return None if state is None else state()


def point(root):
    """Name `root` to the webhost's page (moy_page_at): its state is read
    from the add-on folders there, once, until the next point."""
    try:
        import moy_net
    except ImportError:
        return
    at = getattr(moy_net, "page_at", None)
    if at is not None:
        at(root)


def _now():
    return _ci._ticks_ms()


ROOM_STAMP = "system/addon_room"     # beside the carts folder: the page this store had no room for, and what it needs
ROOM_RECHECK_MS = 5000               # `short` reads the store's free space again no sooner than this
OFFICIAL_STAMP = "system/official"   # beside the carts folder: the page the official carts are at


def official_stamp(root):
    try:
        return _read(_sibling_path(root, OFFICIAL_STAMP)).strip() or None
    except (OSError, ValueError):
        return None


def save_official_stamp(root, want):
    _mkdir(_sibling_path(root, "system"))
    _write_atomic(_sibling_path(root, OFFICIAL_STAMP), want + "\n")


def room_stamp(root):
    """(page digest, bytes) of the add-on a step found no room for, or None."""
    try:
        want, need = _read(_sibling_path(root, ROOM_STAMP)).split()
        return want, int(need)
    except (OSError, ValueError):
        return None


def save_room_stamp(root, want, need):
    _mkdir(_sibling_path(root, "system"))
    _write_atomic(_sibling_path(root, ROOM_STAMP), "%s %d\n" % (want, need))


def official_behind(root, carts):
    """The official entries of `carts` whose cart the store `root` holds at
    an older manifest version (cart_index.cart_state's "update"). Call in a
    store op."""
    out = []
    for c in carts:
        if not _ci.is_official(c):
            continue
        folder = _cart_path(root, c["folder"])
        if not _exists(folder):
            continue
        try:
            man = json.loads(_read(folder + "/manifest.json"))
        except (OSError, ValueError):
            man = None
        if _ci.cart_state(c, None, None, True, man) == "update":
            out.append(c)
    return out


class AddonStep:
    """The add-on that fits this image, installed over the one that does not
    (and with `absent` where there is none and the console was not removed),
    and with `carts` the official carts the store holds brought to the
    release (the module's docstring). `phase` is None while idle; `error` the
    last attempt's failure; `progress` (done, total) while it installs; `due`
    the ticks_ms an attempt was put off at, else None (`poll` starts it once
    its wait is over)."""

    def __init__(self, inst, index, carts=False, absent=False):
        self.inst = inst
        self.index = index
        self.carts = carts
        self.absent = absent
        self.keep = True              # False: no add-on wanted, every one taken off (`drop`)
        self._queue = []
        self._addon = False
        self._stamp = False           # the official stamp, once read (False: unread)
        self._fitless = False         # asking again changes nothing: the release lists
        #                               no add-on for this image, or the store has no room
        self._addon_short = False     # this attempt found the add-on does not fit
        self._room = False            # `short`'s answer (False: unread)
        self._room_at = 0
        self.phase = None
        self.error = None
        self.wake = None              # called when a step starts: tick me each frame
        self._held = False
        self._job = None
        self._fetch = None
        self._gone = None
        self._ended = None
        self._wait = RETRY_MS
        self._pointed = False
        self._removed = None          # the record's console line, once read
        self._removed_at = None       # ...under this page state
        self._tidied = False          # this boot's tidy has run
        self._swept = None            # the folders a tidy takes, rescanned after
        self.due = None
        self._due_ms = 0

    def point(self, again=False):
        """The page's state read from this console's store: once, or `again`
        when a cart may have arrived or gone (the console's screen opening),
        the removal record with it."""
        if again or not self._pointed:
            self._pointed = True
            self._removed = None
            self._room = False
            point(self.inst.root())

    def removed(self):
        """Whether the console's owner removed the browser console
        (moy_seed.addon_removed): read again when the page's state has
        changed since (a removal takes the add-on away) or at a point."""
        state = page_state()
        if self._removed is None or self._removed_at != state:
            root = self.inst.root()
            self._removed = bool(self.inst.op(lambda: _addon_removed(root)))
            self._removed_at = state
        return self._removed

    def restore(self):
        """The console asked for again where it was removed (a Zero's page,
        its only face): the record's line dropped and the step started."""
        root = self.inst.root()
        self.inst.op(lambda: _unremove(root, [_ADDON_LINE]))
        self._removed = None
        return self.nudge()

    def _addon_wanted(self):
        if not self.keep:
            return False
        state = page_state()
        if state == STATE_STALE:
            return True
        return self.absent and state == STATE_ABSENT and not self.removed()

    def wanted(self):
        """An add-on is installed and none of them fits this image, or with
        `absent` none is installed and the console was not removed; or with
        `carts`, the official carts were last brought to another release."""
        self.point()
        return self._addon_wanted() or self._behind()

    def short(self):
        """(bytes needed, bytes free) while the add-on this image names is
        recorded as not fitting the store's free space, else None: the first
        attempt that found no room wrote the record (`system/addon_room`, the
        page digest and the bytes), and the step starts nothing, holds no
        radio and asks no index again until the free space reaches it, which
        a mounted card or deleted carts do. Read again at a `point(again=True)`,
        a `nudge` or a person's start, and otherwise no more often than
        ROOM_RECHECK_MS."""
        now = _now()
        if self._room is not False and _ci._ticks_diff(now, self._room_at) < ROOM_RECHECK_MS:
            return self._room
        self._room_at = now
        self._room = self._short()
        return self._room

    def _short(self):
        want = _ci.page_want()
        if not want or not self._addon_wanted():
            return None
        root = self.inst.root()
        rec = self.inst.op(lambda: room_stamp(root))
        free = self._ask("free")
        if rec is None or rec[0] != want or free is None or free[0] >= rec[1]:
            return None
        return rec[1], free[0]

    def short_text(self):
        """`short` as one line for the screen, or None."""
        got = self.short()
        if got is None:
            return None
        return ("The browser console needs %s and this console has %s free. "
                "Free some space or insert a card." % (_ci.size_text(got[0]),
                                                       _ci.size_text(got[1]) if got[1] > 0 else "nothing"))

    def tidy(self):
        """The image has confirmed itself (call it no sooner): once a boot,
        where the add-on that fits it is installed (the page READY), every
        other add-on folder taken off the shelf by the step's own clean phase,
        no removal recorded. True while that runs (`tick` it)."""
        if self._tidied or self.phase is not None:
            return self.phase is not None
        self._tidied = True
        want = _ci.page_want()
        self.point()
        if self.keep and (not want or page_state() != STATE_READY):
            return False
        keep = PREFIX + want[:12] + ".moy" if self.keep else None
        root = self.inst.root()
        stale = [f for f in self._addons(root) if f != keep]
        if not stale:
            return False
        _ci._log("release: taking %d browser console add-on(s) this firmware "
                 "does not serve off the shelf" % len(stale))
        self._swept = stale
        self._gone = self._removals(root, stale)
        self.error = None
        self.phase = "clean"
        if self.wake is not None:
            self.wake()
        return True

    def drop(self, keep=False):
        """The console's own copy wanted (`keep`) or not: not, every add-on
        folder is taken off the shelf by the step's clean phase (no removal
        recorded: the page is then the loader's, online), as a tidy takes
        the ones that do not fit. True while that runs (`tick` it)."""
        self.keep = keep
        self.absent = keep
        self._room = False
        if keep:
            return self.nudge()
        if self.phase is not None and self.phase != "clean":
            self.stop()
        self._tidied = False
        return self.tidy()

    def _addons(self, root):
        """The add-on folders under `root`: from the shelf the boot scanned
        where the server keeps one (a console's `carts()`), else listed."""
        shelf = getattr(self.inst, "carts", None)
        if shelf is None:
            return installed(root, self.inst.op)
        out = []
        for c in shelf() or ():
            path = c.get("path") if type(c) is dict else None
            name = path.replace("\\", "/").rsplit("/", 1)[-1] if path else ""
            if name.startswith(PREFIX) and name.endswith(".moy"):
                out.append(name)
        return out

    def _ask(self, name):
        fn = getattr(self.inst, name, None)
        return None if fn is None else fn()

    def _put_off(self, ms):
        self.due = _now()
        self._due_ms = ms

    def poll(self, now=None):
        """The console's frame, while `due` is set: the put-off attempt
        started once it is due. True while a step runs."""
        if self.due is None or self.phase is not None:
            return self.phase is not None
        if _ci._ticks_diff(_now() if now is None else now, self.due) < self._due_ms:
            return False
        self.due = None
        return self.start(retry=True)

    def nudge(self):
        """A network was joined: an attempt now, the back-off forgotten."""
        self._ended = None
        self._wait = RETRY_MS
        self._fitless = False
        self._room = False
        self.due = None
        return self.start()

    def _behind(self):
        if not self.carts:
            return False
        want = _ci.page_want()
        if not want:
            return False
        if self._stamp is False:
            root = self.inst.root()
            self._stamp = self.inst.op(lambda: official_stamp(root))
        return self._stamp != want

    def busy(self):
        return self.phase is not None

    @property
    def progress(self):
        job = self._job
        return None if job is None else (job.done, job.total)

    def start(self, retry=False):
        """Begin when the add-on needs it: True while a step runs. `retry`
        waits out the back-off after a failed attempt (a browser asking
        again, the console's put-off attempt); a boot's start and a person's
        button do not. Nothing starts where no network is saved, and a game
        playing puts it off."""
        if self.phase is not None:
            return True
        if retry and (self._fitless or self._ended is not None
                      and _ci._ticks_diff(_now(), self._ended) < self._wait):
            return False
        if self._ask("configured") is False or not self.wanted():
            return False
        if not retry:
            self._room = False          # a person's press or a boot looks again
        addon = self._addon_wanted() and self.short() is None
        if not addon and not self._behind():
            return False                # the add-on has no room, the carts nothing to do
        if self._ask("playing"):
            self._put_off(RETRY_MS)
            return False
        url = self.index() if callable(self.index) else self.index
        if not url:
            self.error = "no update address"
            self._ended = _now()
            return False
        self._url = url
        self.error = None
        self.phase = "online"
        if not self._held:
            self._held = True
            self.inst.hold()
        self._addon = addon
        _ci._log("release: bringing %s to this firmware"
                 % ("the browser console add-on" if self._addon else "the official carts"))
        if self.wake is not None:
            self.wake()
        return True

    def stop(self, release=True):
        """Drop the step, the shelf as it was. `release` False leaves the
        radio's hold to whoever takes the same lease now."""
        job, self._job = self._job, None
        if job is not None:
            if not job.cancel():
                job.finish()            # past the point of no return: it lands
            while not job.finished and job.step():
                pass
        if self._fetch is not None:
            self._fetch.close()
            self._fetch = None
        self._gone = None
        if self._swept is not None:
            self._swept = None
            self._tidied = False        # the next tidy takes the rest
        self._queue = []
        self.phase = None
        if self._held:
            self._held = False
            if release:
                self.inst.release()

    def tick(self, budget_ms=STEP_MS):
        """One frame's share: True while the step wants the next frame. A
        game that starts stops it, to start again after it."""
        if self.phase is None:
            return False
        if self._ask("playing"):
            self.stop()
            self._put_off(RETRY_MS)
            return False
        try:
            return getattr(self, "_" + self.phase)(budget_ms)
        except Exception as exc:  # noqa: BLE001 -- the step never takes a frame down
            return self._end(getattr(exc, "text", None) or repr(exc))

    def _online(self, _budget):
        net = self.inst.net()
        if net is None:
            return self._end("no network")
        ready = getattr(net, "ready", None)
        up = ready() if ready is not None else net.online()
        if up is None:
            return True
        if not up:
            return self._end("WiFi isn't connected.")
        self._fetch = _ci.index_fetch(net, self._url)
        self.phase = "index"
        return True

    def _index(self, _budget):
        if self._fetch.step():
            return True
        data, self._fetch = self._fetch.data, None
        carts = _ci.fitting(_ci.parse_index(data, self._url, self._url))
        self._queue = []
        self._addon_short = False
        if self._addon:
            fits = [c for c in carts if c.get("runtime") == "web"]
            if not fits:
                # The release does not change under its image: asking again
                # until a person or a boot does is a fetch of the index a
                # minute for nothing.
                self._fitless = True
                return self._end("no browser console for this firmware")
            short = self._fits_room(fits[0])
            if short is None:
                self._keep = fits[0]["folder"]
                self._queue.append(fits[0])
            else:
                self._addon = False
        if self.carts:
            root = self.inst.root()
            self._queue += self.inst.op(lambda: official_behind(root, carts))
        if self._addon_short and not self._queue:
            return self._end(None, short=True)
        self.phase = "install"
        return self._next_job()

    def _fits_room(self, cart):
        """None when `cart`, the add-on, fits the store's free space (or the
        store cannot say), else (bytes needed, bytes free), recorded
        in the store: nothing asks for the add-on again until the room is
        there (`short`)."""
        free = self._ask("free")
        if free is None:
            return None
        chip, fmt = self.inst.chip()
        ranges = bool(getattr(self.inst.net(), "ranges", False))
        need = _ci.need_bytes(_ci.plan(cart, chip, fmt, ranges), free[1])
        if _ci.room_why(need, free[0]) is None:
            return None
        root, want = self.inst.root(), _ci.page_want()
        if want:
            self.inst.op(lambda: save_room_stamp(root, want, need))
        self._room, self._room_at = (need, free[0]), _now()
        self._fitless = True
        self._addon_short = True
        return need, free[0]

    def _next_job(self):
        """The next cart of the queue's install started: False when none is
        left, the step then ending."""
        if not self._queue:
            return self._done()
        cart = self._queue.pop(0)
        chip, fmt = self.inst.chip()
        ranges = bool(getattr(self.inst.net(), "ranges", False))
        self._job = _ci.Install(cart, _ci.plan(cart, chip, fmt, ranges), self.inst.net(),
                                self.inst.root(), self.inst.op)
        return True

    def _install(self, budget):
        job = self._job
        if job.step(budget):
            return True
        self._job = None
        if not job.path:
            return self._end(job.error or "stopped")
        if job.cart.get("runtime") != "web":
            self.inst.rescan(job.path)
        return self._next_job()

    def _done(self):
        """Every install landed: the official stamp, then the add-ons that no
        longer fit taken away."""
        root = self.inst.root()
        if self.carts:
            want = _ci.page_want()
            if want:
                self.inst.op(lambda: save_official_stamp(root, want))
                self._stamp = want
        if not self._addon:
            return self._end(None)
        old = [f for f in installed(root, self.inst.op) if f != self._keep]
        self._gone = self._removals(root, old)
        self.phase = "clean"
        return True

    def _removals(self, root, folders):
        for f in folders:
            yield from _ci.stepped(self.inst.op, _ci.remove_steps(root, f))

    def _clean(self, _budget):
        if next(self._gone, _ci._DONE) is not _ci._DONE:
            return True
        self._gone = None
        swept, self._swept = self._swept, None
        if swept is None:
            self.inst.rescan(None)
            self.point(again=True)      # the webhost reads the new pack's head
            return self._end(None)
        for f in swept:
            self.inst.rescan(f)
        if not self.keep:
            self.point(again=True)      # no copy left: the page is the loader's
        self.phase = None
        return False

    def _end(self, error, short=False):
        self.phase = None
        self.error = error
        if error is None:
            self._ended = None
            self._wait = RETRY_MS
            if short:
                _ci._log("release: the browser console add-on does not fit the "
                         "store's free space: not fetched until there is room")
            else:
                _ci._log("release: this firmware's browser console add-on and official "
                         "carts are installed")
        else:
            if self._ended is not None:
                self._wait = min(self._wait * 2, RETRY_MAX_MS)
            self._ended = _now()
            if not self._fitless:
                self._put_off(self._wait)
            _ci._log("release: %s" % error)
        if self._job is not None:
            self._job = None
        if self._held:
            self._held = False
            self.inst.release()
        return False


ASK_MS = 600000                 # an install prompt no page answers is cancelled after this
WRONG_PASSWORD = "That isn't the console's password."


class OfficialCarts:
    """`/official`'s backend on every board (a Zero's zero_host.make_official,
    a console's moy_webhost.console_official): the carts of the indexes
    this board browses (cart_index.load_indexes: its
    `system/sources`, else moybyte-org/carts, and its own release's index,
    `index`, a url or a callable answering one), listed for the page it
    serves and installed or removed when that page asks. The route keeps the
    name it had when it listed the release's official carts alone. The page
    asks and the board does the work, a slice per poll (`step`), as
    zero_host.ZeroUpdate updates its firmware: a POST queues and answers at
    once (`request`), a GET reads where it stands (`answer`).

      check    the shelves this board reads, answered at once with no
               fetch (`shelves`): their urls, its own release's (`own`), the
               keys it checks an index's signature with (`keys`,
               cart_index.index_keys), its install record (`record`), its
               chip, format and ranged reads (`chip`, `fmt`, `ranges`), the
               store's room (`free`) and whether it has a password
               (`locked`). The page fetches each index and lists it by the
               VM's own rules (carts_link.BoardCheck), the board's heap
               holding none of it; its own release's from the mirror
               (cart_index.index_mirror), checked with `keys`.
               With `index`, one of those shelves the page cannot read
               itself: that index fetched (its signature checked, as a
               console's Get Carts reads it) and its entries that fit this
               image listed (cart_index.listing) but the browser console add-on,
               which the board keeps itself (AddonStep), each with where it
               stands in this store, with the store's room, whether it was
               reached and `locked`. Either is "listed", handed to the next
               GET once, then "idle"
      licence  the licence of the external file `path` of the entry
               `folder` (and `id`) of the index `index`, read as `install`
               reads it:
               "listed" with its `text`, likewise
      install  that index's entry read as the index streams
               (cart_index.EntryRead; the release's from its mirror first,
               then the release) and installed through cart_index.Install (its saves and an edited config carried,
               the external files the page `accepted` the licence of), once
               the store has room for it: the checked build's manifest is
               handed to the page ("asking", `manifest`) for the install
               prompt (pkg.manifest_check), and `agree` lands it: "done"
      agree    the page's prompt answered yes; for a Python cart from an
               index that is not reviewed (cart_index.is_reviewed), on a
               board with a password (`locked()`), with that `password`,
               which `unlock(password)` checks: a wrong one stops the
               install (WRONG_PASSWORD)
      remove   an optional built-in's removal recorded (moy_seed.note_removed,
               as pkg.removed records it), or a cart the store's record
               holds, and its folder taken off: "done"; a core cart, or one
               nothing installed, is refused
      cancel   an install stopped while it can be
      offline  `{"on": bool}`: the browser console's own copy in the store
               or not, where the board's console is online and `offline`
               (zero_offline.Offline) makes it a choice; the GET's "offline"
               says where that stands

    `index` names one of the indexes the board browses; none is its own
    release's. A version an index revoked is refused (cart_index.REVOKED),
    and an install whose cart and external files need more room
    than the store has free less `reserve` (zero_host.SEED_RESERVE) is
    refused before anything is fetched, with the sizes
    (cart_index.room_why).

    Everything a request makes -- the indexes, the list, the install's
    buffers -- is made for it and let go when it ends, so an idle board
    holds none of it. An install holds one entry of its index, never the
    index, and its buffers are sized to the heap it finds (install_chunk). `busy()` (the release's own AddonStep) holds a request
    back: two installs never write one store. `sources(root, own)` answers
    the indexes (cart_index.load_indexes)."""

    def __init__(self, inst, index, busy=None, reserve=0, sources=None, locked=None,
                 unlock=None, offline=None):
        self.inst = inst
        self.offline = offline        # the console's own copy, where it is a choice (`Offline`)
        self.locked = locked          # () -> whether this board has a password
        self.unlock = unlock          # (password) -> whether it is this board's
        self.index = index
        self.other = busy
        self.reserve = reserve
        self.sources = sources or _ci.load_indexes
        self.state = "idle"
        self.action = None
        self.folder = None
        self.error = None
        self._listed = None
        self._phase = None
        self._urls = None
        self._from = None
        self._want = None
        self._fetch = None
        self._found = None
        self._unreached = 0
        self._job = None
        self._gone = None
        self._asked_at = None
        self._held = False
        self._cancelled = False

    def busy(self):
        return self.state in ("checking", "installing", "removing")

    def _own(self):
        return self.index() if callable(self.index) else self.index

    def _indexes(self):
        root = self.inst.root()
        own = self._own()
        return self.inst.op(lambda: self.sources(root, own))

    # -- the request side -----------------------------------------------------

    def request(self, action, folder=None, doc=None):
        """Queue `check`, `licence`, `install`, `agree`, `remove` or
        `cancel` (`doc` the POST's other members: `index`, `id`,
        `accepted`, `path`): (ok, message)."""
        doc = doc if isinstance(doc, dict) else {}
        if action == "cancel":
            return self._cancel()
        if action == "agree":
            return self._agree(doc.get("password"))
        if action == "offline" and self.offline is not None:
            return self.offline.choose(bool(doc.get("on")))
        if action not in ("check", "licence", "install", "remove"):
            return False, "action must be check, licence, install, agree, remove or cancel"
        if self.busy():
            return False, "busy: " + self.state
        if self.other is not None and self.other():
            return False, "busy: the release's own install"
        if action != "check" and not (isinstance(folder, str) and _ci.plain_name(folder)
                                      and folder.endswith(".moy")):
            return False, "no cart folder named"
        self._listed = None
        self.error = None
        self.action = action
        self.folder = folder
        self._cancelled = False
        root = self.inst.root()
        if action == "remove":
            import moy_carts
            if moy_carts.is_core(folder):
                return False, "%s stays on this console" % folder
            if not self.inst.op(lambda: _exists(_cart_path(root, folder))):
                return False, "%s isn't on this console" % folder
            if not moy_carts.removable(folder) \
                    and folder not in self.inst.op(lambda: _ci.load_record(root)):
                return False, "%s wasn't installed from a shelf" % folder
            self.state = "removing"
            self._gone = self._removal(root, folder)
            return True, "queued"
        urls = self._indexes()
        if action == "check" and doc.get("index") is None:
            self._listed = self._shelves(root, urls)
            self.state = "listed"
            return True, "listed"
        if action == "check":
            if doc["index"] not in urls:
                return False, "it isn't on a shelf this console reads"
            self._urls = [doc["index"]]
        else:
            url = doc.get("index") or self._own()
            if not url or url not in urls:
                return False, "it isn't on a shelf this console reads"
            accepted = doc.get("accepted") or ()
            if not isinstance(accepted, (list, tuple)) \
                    or not all(isinstance(a, str) for a in accepted):
                return False, "accepted must be a list of paths"
            path = doc.get("path")
            if action == "licence" and not isinstance(path, str):
                return False, "no external file named"
            self._urls = [url]
            mirror = _ci.index_mirror(url) if url == self._own() else None
            self._from = [mirror, None] if mirror else [None]
            self._want = (doc.get("id"), tuple(accepted), path,
                          "It isn't in this console's release." if url == self._own()
                          else "It isn't on that shelf.")
        self._found = []
        self._unreached = 0
        self.state = "checking" if action != "install" else "installing"
        self._phase = "online"
        if not self._held:
            self._held = True
            self.inst.hold()
        return True, "queued"

    def _shelves(self, root, urls):
        """The `shelves` document a check answers with (the class's
        docstring): what a page needs to list this board's shelves itself."""
        chip, fmt = self.inst.chip()
        return json.dumps({
            "shelves": urls, "own": self._own(), "keys": _ci.index_keys(),
            "record": self.inst.op(lambda: _ci.load_record(root)),
            "chip": chip, "fmt": fmt,
            "ranges": bool(getattr(self.inst.net(), "ranges", False)),
            "free": self.inst.op(lambda: _room(root, self.reserve)),
            "locked": self._locked()})

    def _cancel(self):
        job = self._job
        if self.state != "installing":
            return False, "nothing to cancel"
        if job is not None and not job.cancel():
            return False, "it is landing"
        self._cancelled = True
        if job is None:
            self._end(None)             # nothing written yet: stopped now
        return True, "cancelled"

    def _locked(self):
        return self.locked is not None and bool(self.locked())

    def _agree(self, password=None):
        job = self._job
        if self.state != "installing" or job is None or job.asking is None:
            return False, "nothing is asking"
        cart = job.cart
        if cart.get("runtime") == "python" and not _ci.is_reviewed(cart) \
                and self._locked() and not (isinstance(password, str) and password
                                            and self.unlock is not None
                                            and self.unlock(password)):
            job.cancel()
            self._asked_at = None
            return False, WRONG_PASSWORD
        job.agree()
        self._asked_at = None
        return True, "agreed"

    # -- what a GET reads ------------------------------------------------------

    def answer(self, ok=None, message=None):
        """The /official document as JSON text: the state ("asking" while an
        install waits on the page's prompt, its `manifest` beside it), the
        request it is about, the install's progress, the error; a check's
        list or a licence's text the once a GET reads them."""
        job = self._job
        asking = job is not None and job.asking is not None
        doc = {"state": "asking" if asking else self.state, "action": self.action,
               "folder": self.folder, "error": self.error, "progress": None}
        if job is not None:
            doc["progress"] = [job.done, job.total]
        if asking:
            doc["manifest"] = job.asking
        if ok is not None:
            doc["ok"] = ok
            doc["message"] = message
        if self.offline is not None:
            doc["offline"] = self.offline.state()
        text = json.dumps(doc)
        listed = self._listed
        if listed is not None and ok is None:
            self._listed = None
            self.state = "idle"
            text = text[:-1] + ", " + listed[1:]
        return text

    # -- the pumped side -------------------------------------------------------

    def step(self, budget_ms=STEP_MS):
        """One slice of the request in hand: True while it wants the next
        (False while an install waits on the page's prompt, which the poll
        still steps while `busy()`)."""
        try:
            if self.state == "removing":
                if next(self._gone, _ci._DONE) is not _ci._DONE:
                    return True
                self._gone = None
                return self._end(None)
            if self._phase is None:
                return False
            return getattr(self, "_" + self._phase)(budget_ms)
        except MemoryError as exc:
            _ci._log("official: %s in %s" % (exc, self._phase))
            return self._end(_ci.NO_MEMORY)
        except Exception as exc:  # noqa: BLE001 -- a request never takes the host down
            _ci._log("official: %s in %s" % (getattr(exc, "detail", None) or repr(exc),
                                              self._phase))
            return self._end(getattr(exc, "text", None) or repr(exc))

    def _online(self, _budget):
        net = self.inst.net()
        if net is None:
            return self._end("no network")
        ready = getattr(net, "ready", None)
        up = ready() if ready is not None else net.online()
        if up is None:
            return True
        if not up:
            return self._end("WiFi isn't connected.")
        self._phase = "index"
        return True

    def _index(self, budget):
        """The next index fetched and read, a fetch's step a poll."""
        if self.action != "check":
            return self._entry(budget)
        if self._fetch is None:
            if not self._urls:
                return self._indexed()
            self._fetch = _ci.index_fetch(self.inst.net(), self._urls[0])
        url = self._urls[0]
        try:
            if self._fetch.step():
                return True
            data = self._fetch.data
            self._fetch = None
            self._urls.pop(0)
            got = [c for c in _ci.fitting(_ci.parse_index(data, url, self._own()))
                   if c["runtime"] != "web"]
        except _ci.InstallError as exc:
            self._fetch = None
            if self.action != "check":
                raise
            self._urls.pop(0)
            self._unreached += 1
            _ci._log(exc.detail)
            return True
        data = None
        self._found.append(self._listings(got))
        return True

    def _entry(self, budget):
        """The entry asked for read as its index streams, from the release's
        mirror first where it has one: a mirror that cannot be read, or
        does not list the entry, hands the read to the release."""
        if self._fetch is None and not self._urls:
            return self._indexed()
        url = self._urls[0]
        if self._fetch is None:
            self._fetch = _ci.EntryRead(self.inst.net(), url, self.folder, self._want[0],
                                        self._own(), self._from[0])
        try:
            if self._fetch.step(budget):
                return True
            got = [c for c in _ci.fitting(self._fetch.carts) if c["runtime"] != "web"]
        except _ci.InstallError as exc:
            self._fetch = None
            if len(self._from) == 1:
                raise
            _ci._log("official: %s; the release instead" % exc.detail)
            self._from.pop(0)
            return True
        self._fetch = None
        if not got and len(self._from) > 1:
            self._from.pop(0)
            return True
        self._found.extend(got)
        self._urls.pop(0)
        return True

    def _listings(self, carts):
        """`carts` as the page lists them (cart_index.listing), each with where it
        stands in this store: one JSON text, so the index's entries go."""
        root = self.inst.root()
        chip, fmt = self.inst.chip()
        ranges = bool(getattr(self.inst.net(), "ranges", False))

        def _scan():
            rec = _ci.load_record(root)
            out = []
            for c in carts:
                p = _ci.plan(c, chip, fmt, ranges)
                folder = _cart_path(root, c["folder"])
                present = _exists(folder)
                entry = rec.get(c["folder"])
                man = None
                if present and (entry is None or entry.get("id") != c["id"]
                                or _ci.is_official(c)):
                    try:
                        man = json.loads(_read(folder + "/manifest.json"))
                    except (OSError, ValueError):
                        man = None
                out.append(json.dumps(_ci.listing(c, _ci.cart_state(c, p, entry, present, man),
                                              entry.get("version") if entry else None)))
            return out
        return ", ".join(self.inst.op(_scan))

    def _indexed(self):
        """Every index read: a check's list handed over, else the one
        entry asked for licensed or installed."""
        found, self._found = self._found, None
        root = self.inst.root()
        room = self.inst.op(lambda: _room(root, self.reserve))
        if self.action == "check":
            if found == [] and self._unreached:
                return self._end(_ci.UNREACHABLE)
            parts = [f for f in found if f]
            listed = '{"carts": [%s], "free": %s, "unreached": %d, "locked": %s}' % (
                ", ".join(parts), json.dumps(room), self._unreached,
                "true" if self._locked() else "false")
            self._release()
            self._phase = None
            self._listed = listed
            self.state = "listed"
            _ci._log("official: %d bytes listed" % len(listed))
            return False
        cart = found[0] if found else None
        found = None
        _id, accepted, path, missing = self._want
        if cart is None:
            return self._end(missing)
        if not _ci.runs_on(cart, _ci.RUNTIMES):
            return self._end("This console can't play this kind of cart.")
        if _ci.newer_why(cart) is not None:
            return self._end(_ci.newer_why(cart))
        if _ci.is_revoked(cart):
            return self._end(_ci.REVOKED)
        if self.action == "licence":
            ext = None
            for e in cart.get("external") or ():
                if e["path"] == path:
                    ext = e
            if ext is None:
                return self._end("It needs no file of that name.")
            self._fetch = _ci.licence_fetch(self.inst.net(), cart, ext["licence"])
            self._phase = "licence"
            return True
        chip, fmt = self.inst.chip()
        ranges = bool(getattr(self.inst.net(), "ranges", False))
        p = _ci.plan(cart, chip, fmt, ranges)
        keep, arc = _archive_keep(p)
        if room is not None:
            why = _ci.room_why(_ci.need_bytes(p, room[1]) + (arc if keep == "store" else 0),
                               room[0])
            if why is not None:
                return self._end(why)
        read, chunk = install_chunk()
        self._job = _ci.Install(cart, p, self.inst.net(), root, self.inst.op, accepted,
                                chunk=chunk, read=read, archive=keep, ask=_manifest_of)
        self._phase = "install"
        return True

    def _licence(self, _budget):
        if self._fetch.step():
            return True
        text = _ci.as_text(self._fetch.data)
        self._fetch = None
        self._listed = json.dumps({"text": text})
        self._release()
        self._phase = None
        self.state = "listed"
        return False

    def _install(self, budget):
        job = self._job
        if job.step(budget):
            if job.asking is None:
                return True
            if self._asked_at is None:          # the page's turn: nothing to do here
                self._asked_at = _now()
                self._release()
            elif _ci._ticks_diff(_now(), self._asked_at) > ASK_MS:
                self._asked_at = None
                job.cancel()
                return True
            return False
        self._asked_at = None
        if not job.path:
            return self._end(None if self._cancelled else (job.error or _ci.STOPPED))
        import moy_carts
        root = self.inst.root()
        folder = self.folder
        self.inst.op(lambda: moy_carts.unremove(root, [folder]))
        self.inst.rescan(job.path)
        return self._end(None)

    def _removal(self, root, folder):
        import moy_carts
        self.inst.op(lambda: moy_carts.note_removed(root, folder))
        yield
        yield from _ci.stepped(self.inst.op, _ci.remove_steps(root, folder))
        self.inst.rescan(folder)

    def _release(self):
        if self._held:
            self._held = False
            self.inst.release()

    def _end(self, error):
        self._phase = None
        if self._fetch is not None:
            self._fetch.close()
            self._fetch = None
        self._found = None
        self._urls = None
        self._job = None
        self._release()
        self.error = error
        if self._cancelled:
            self.state = "idle"
        else:
            self.state = "done" if error is None else "error"
        _ci._log("official: %s %s %s" % (self.action, self.folder or "",
                                         error or self.state))
        return False


ARCHIVE_RAM_SHARE = 4           # an external archive kept in RAM below this share of the free heap


# An install's buffers on a heap that cannot hold cart_index's own
# (READ_CHUNK, WRITE_CHUNK) eight times over: a C3 Zero's, whose Python heap is
# smaller than one WRITE_CHUNK.
SMALL_CHUNK = 4096


def install_chunk():
    """(read, write): the buffer sizes an install takes on the heap free
    now, cart_index's own where it holds them eight times over, else
    SMALL_CHUNK each."""
    try:
        import gc
        free = gc.mem_free()
    except (ImportError, AttributeError):
        return _ci.READ_CHUNK, _ci.WRITE_CHUNK
    if free >= 8 * (_ci.READ_CHUNK + _ci.WRITE_CHUNK):
        return _ci.READ_CHUNK, _ci.WRITE_CHUNK
    return SMALL_CHUNK, SMALL_CHUNK


def _archive_keep(p):
    """("ram" or "store", the external archives' bytes) for plan `p`: an
    archive goes through the store where the heap has less than
    ARCHIVE_RAM_SHARE times it free, and the room check counts it."""
    arc = 0
    for e in p["external"]:
        if _ci.external_mirror(e) is None:
            arc += e["archive"]["size"]
    if not arc:
        return "ram", 0
    try:
        import gc
        free = gc.mem_free()
    except (ImportError, AttributeError):
        return "ram", arc
    return ("store" if free < ARCHIVE_RAM_SHARE * arc else "ram"), arc


def _manifest_of(stage):
    """The install's `ask`: the checked build's manifest, which the page's
    install prompt reads (pkg.manifest_check); never None, so the install
    waits for the page."""
    try:
        man = json.loads(_read(stage + "/manifest.json"))
    except (OSError, ValueError):
        man = None
    return man if isinstance(man, dict) else {}


def _room(root, reserve):
    """(bytes an install may take, block size) of the store `root` with
    `reserve` kept free, or None where it cannot say."""
    import os
    try:
        st = os.statvfs(root)
    except (OSError, AttributeError):
        return None
    return max(0, st[0] * st[3] - reserve), st[0]
