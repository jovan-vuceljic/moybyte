# Map (grep -n a name to jump there):
#   fill                          the page's states from the app's phase
#   build                         the page: the shelf, the desk's pane, a cart's page, the rest
#   GetCartsAppLayer              the Get Carts app: index, covers, install
#   GetCartsAppLayer._pump        one frame's slice of fetching and installing
#   GetCartsAppLayer._build_rows  the index's carts as rows
#   GetCartsAppLayer.blocker      why a row cannot be installed here
#   GetCartsAppLayer.draw         the app's frame: its work's slice, then the page
"""Get Carts -- the console's store (#124): carts other people publish,
browsed and installed over WiFi with no PC involved, a `uitree` page the C
engine lays out and paints (`build`), its states written from the app's
phase each drawn frame (`fill`).

The screens, in the order a kid meets them:

  CHECKING   the radio comes up under the "carts" lease and every index is
             fetched -- moybyte-org's carts repository unless `system/sources`
             names others (runtime/shell/pkg.py, the shell's `pkg`) --
             one busy page, the shelves counted as they come.
  LIST       the shelf: a card per cart, its cover (the 128 x 128
             cover.png of SPEC.md 3.6, which the card names: `cover_pic`)
             -- a cart on the console its copy's, drawn from the shell's
             cover cache (`image.cart`) with no network; any other the
             index's, fetched after the shelf shows, the cards in view
             first, and handed to the engine as the app's own picture
             (`ui.pictures`), kept for the boot -- a still "on its way"
             picture while it comes, and where it has none (or it failed)
             its genre's icon on a tinted tile, its
             name and a sub line -- its size, or where it stands: On
             console, Update ready, Name taken when a different cart already
             has its folder, Too big or Can't play. The caption row counts
             them and says what room is free; R checks again (on the desk,
             Check).
  CART       one cart: its cover, genre and source, where it stands, its
             description, what it takes and needs, and its verbs -- Remove,
             Play (a theme package's ("runtime": "theme") Use, which makes it
             the console's theme; removing the active one falls back to the
             default seed, the look's `store_moved`), Get or Update. A cart
             that will not fit in the store, that the engine would refuse to
             load (the Player's check, asked of the index before the
             download), or that this console cannot play says why and offers
             no Get. Remove asks first, in a dialog. On the desk the page is
             a pane beside the shelf, for the card focus is on, its verbs in
             the window's foot.
  LICENCE    a file the cart needs that is not in its release (Doom's WAD)
             shows its licence before it is fetched. No has the focus; I
             agree is the only way on.
  INSTALL?   the install prompt (runtime/shell/app_perms.py), once every
             file is checked and before anything moves onto the shelf: a
             dialog over the download naming what the cart can reach, No
             first. Install puts it on the shelf with every permission it
             lists and records that consent; No (B, Esc) removes the build,
             and the shelf is as it was. A cart that asks for nothing a game
             does not, or an update that adds nothing, is not asked about.
             One that requires what this console lacks is not installed.
             It names the publisher first. A Python cart from an index
             nobody reviewed carries the unreviewed warning (app_perms.
             UNREVIEWED), and where the console has a password a field
             under it takes that password before Install goes on (pkg.
             gated); one typed wrong keeps the prompt up, saying so. A
             version its index took back is not installed, and one on the
             console says so (Taken back), offering only Remove.
  YOUR COPY  a console that can be handed a file (the browser) first asks
             whether it can read that file from anywhere the index names --
             its mirror beside the index, then its archive's hosts; where it
             cannot, the player chooses their own copy, which is held to the
             index's size and sha256 before anything is downloaded.
  GETTING    the download, a slice per frame (`cart_index.Install.step`), with
             its progress and Cancel, which B (Esc) or a tap reaches and A
             never does (a kid presses A twice after Get) -- until the build
             is checked and goes to a store of record that is not these files
             (the browser's), when it can no longer be cancelled and says so.
  READY / NOT INSTALLED  how it ended: the cart's page again under a toast,
             Play first; or the reason, and that nothing changed on the shelf.
  WI-FI IS OFF, SHELF AWAY, MEMORY FULL, NO INTERNET  why there is no shelf,
             and Try again; with Wi-Fi off, Wi-Fi opens the Wi-Fi page and
             coming back from it checks again at once.
  ON THE CONSOLE  a page a board serves that answers no /official (an
             older image): the carts it shows are the board's, and the
             board gets its own, so this one fetches nothing.
  A BOARD'S PAGE  a page a console serves that answers /official
             (`install.board()`): the shelf is the carts of that console's
             shelves (its sources and its own release), which this page
             fetches and reads itself (carts_link.BoardCheck), each
             where it stands in that console's store, its room the
             console's, and a licence, Get and Remove ASK it -- it fetches
             and checks, the page shows the licence and the install prompt
             (`pkg.manifest_check` over the manifest it checked), and it
             writes its own store, the page waiting with its progress,
             then brings its copy of the cart over this page's. A cover
             shows for a cart the console holds.

The installing is cart_index's; this module is the screens and the lease. The
radio is held while something is fetched -- the indexes, a licence and the
download it leads to -- and let go as soon as that ends: never while the kid
browses, never into a cart (Play lets go first), never past `close()`.

Work that may wait (dialling the network, fetching an index) runs one frame
after its screen is shown, so CHECKING is on the glass before the wait starts
-- the update screen's arm (runtime/system/update_ui.py). Every fetch is a
`cart_index` job stepped once a frame, which on a board or the host finishes
in that step and in the browser gives the frame back until its bytes come.
"""

import json
from array import array

import uitree as ui
import uitree_app
import app_perms as _perms
import cart_index as _ci
import cart_listing as _cl
import moy_store
from ticks import _ticks_ms, _ticks_diff
import pkg as _pkg
import moy_carts as _store


# An index fetched this session is reused for this long before the app checks
# again on its own; R (the desk's Check) asks at once.
REFRESH_MS = 600000

# The cover fetches asked of the http worker at once: it goes from one to the
# next with no frame between them.
COVERS_AHEAD = 2

# The own picture a card shows while its cover is on its way.
WAIT = "wait"

# The check's piece of a frame: an index is parsed and the shelf's rows are
# made in pieces of about this long, a frame between them, so a long index
# never holds the screen (cart_index.parse_steps).
CHECK_MS = 40

# Where a card stands, as its sub line and its badge say it; a cart that is
# only for the getting says its size instead.
STATE_WORD = {"installed": "On console", "update": "Update ready", "taken": "Name taken",
              "revoked": "Taken back", "too_big": "Too big", "noplay": "Can't play",
              "newer": "Needs update"}
BADGE = {"installed": "check", "update": "getcarts", "taken": "warn", "revoked": "warn",
         "too_big": "warn", "noplay": "warn", "newer": "warn"}
# The states a card's sub line and badge say in the danger ink, its cover veiled.
BLOCKED = ("taken", "revoked", "too_big", "noplay", "newer")

# The shelf caption's words when an index lists the browser console for other
# builds and none for this image's page: an image its release did not publish
# (cart_index.addon_unfit). Every other cart lists whatever the build.
NO_ADDON = "no browser console for this build"

# A verb's words, icon and action, by its name.
VERB = {"GET": ("Get", "getcarts", "get"), "UPDATE": ("Update", "getcarts", "update"),
        "PLAY": ("Play", "play", "play"), "USE": ("Use", "palette", "use"),
        "REMOVE": ("Remove", "trash", "remove"), "I AGREE": ("I agree", "", "agree"),
        "NO": ("No", "", "no"), "CANCEL": ("Cancel", "close", "cancel"), "OK": ("OK", "", "ok"),
        "TRY AGAIN": ("Try again", "rotate", "try_again"), "WIFI": ("Wi-Fi", "wifi", "wifi")}

# What the install prompt says over its password field (pkg.gated).
PASSWORD_LINE = "A grown-up types the console's password to say yes:"

# The id focus rests on while work is in hand: no stop, so Enter acts on none.
_NOWHERE = "nowhere"

# A toast stays this long, or until the next key.
TOAST_MS = 2000

# An external file's archive is held in RAM while it is checked and unpacked
# when it is under this share of the largest free block a compiled cart loads
# into, and kept in a file beside the build otherwise. The P4s' 32 MB clear it
# (and their flash store writes slowly); on an S3 the archive would sit in a
# Python heap that never shrinks, out of reach of the cart it was fetched for
# until a reboot, while its card writes fast.
ARCHIVE_RAM_SHARE = _pkg.ARCHIVE_RAM_SHARE

# The phases whose work runs a slice per frame from draw().
BUSY = ("checking", "licence_fetch", "probing", "picked", "connecting", "getting")
# The phases past the list that are pages of their own (`has_page`).
_PAGES = ("licence", "pick", "cart", "done", "failed", "consent")
# The pages that say why there is no shelf, and Try again.
_AWAY = ("nonet", "nowifi", "unreached", "nomemory")


_mb = _pkg.size_text


def _asked(job):
    """`yield from` it: a request to a console with no screen
    (carts_link.BoardAsk) stepped a frame a step; its refusal raised."""
    while job.step():
        yield
    if job.error is not None:
        raise _ci.InstallError(job.error, getattr(job, "detail", None))


def _host_of(url):
    start = url.find("://")
    rest = url[start + 3:] if start >= 0 else url
    cut = rest.find("/")
    return rest if cut < 0 else rest[:cut]


def _ext_host(cart, e):
    """Where an external file comes from first, as the screens name it: its
    mirror's host, else its archive's."""
    return _host_of(_ci.resolve(cart["index"], _ci.external_sources(e)[0]))


def _any_key(inp):
    for k in ("a", "b", "up", "down", "left", "right"):
        if inp.pressed(k):
            return True
    return False


def vid(verb):
    """A verb's action: its button's stop."""
    return VERB[verb][2]


def _wait_render(lay):
    """The "on its way" picture at a card's size: three dots in the theme's
    dim ink over its alt surface, which `clear=True` leaves out, so the
    card's own tile shows under them."""
    def render(w, h):
        th = lay._theme.colors()
        layer = lay._surf.canvas().new_layer(w, h)
        layer.rect(0, 0, w, h, th["surface_alt"])
        r = max(2, w // 28)
        cx, cy = w // 2, h // 2
        for dx in (-4 * r, 0, 4 * r):
            layer.circ(cx + dx, cy, r, th["ink_dim"])
        return layer
    return render


def genre_icon(cart):
    """The icon a cart with no cover shows: a theme's palette, music's
    note, an app's window, else the gamepad."""
    if cart.get("runtime") == "theme":
        return "palette"
    g = cart.get("genre")
    if g == "music":
        return "music"
    if cart.get("type") == "app":
        return "app"
    return "game"


# -- the page ---------------------------------------------------------------------

_LINE = dict(key="id", id="", text="", tone="")
s = ui.state(
    # the page a phase shows (`fill`): the desk's is the shelf beside the pane
    view=ui.enum("shelf", "desk", "cart", "getting", "licence", "pick", "busy", "words", init="shelf"),
    caption="",                 # the shelf's count and its room free, on the desk's one line
    count="",                   # ...on the handheld's: the count at its start, the room at its end
    free="",
    carts=ui.model(key="id", id="", name="", sub="", icon="", tone="", badge="", pic=ui.IMAGE),
    card=ui.row_of("carts"),
    none=False,                 # the shelf is empty
    shown=False,                # the desk's pane has a cart
    name="",                    # the cart: its name, its cover's tile, where it is from
    icon="game",
    pic=ui.IMAGE,               # ...its cover, None while it has none (the icon's tile)
    meta="",
    genre="",
    src="",
    state="",                   # ...where it stands
    state_icon="",
    state_tone="",
    desc="",
    facts=ui.model(key="id", id="", label="", value=""),
    busy=False,                 # the desk's pane shows the work in hand
    title="",                   # the work in hand, or a page's title
    line="",
    done=0,
    total=0,
    bar=False,                  # ...its size known
    what="Downloading",
    counting=False,             # the check's shelves counted
    step=0,
    steps=1,
    shelf="",
    status="",                  # the desk's foot: the cart and where it stands
    get_ok=True,                # no blocker stops Get
    play_ok=True,               # the cart is on the console
    v_get=False, v_update=False, v_play=False, v_use=False, v_remove=False, v_agree=False,
    v_no=False, v_cancel=False, v_ok=False, v_try_again=False, v_wifi=False,
    words_icon="getcarts",
    lines=ui.model(**_LINE),    # Your copy's lines
    w0="", w1="", w2="", w3="",  # a words page's paragraphs
    licence_name="",
    licence="",
    toast="",
    toast_icon="",
    asking=False,               # Remove's dialog
    rm_title="",
    consent=False,              # the install prompt
    q_title="",
    perms=ui.model(**_LINE),
    gated=False,
    pw_line="",
    pw_tone="dim",
    password="",
)
ui.app("Get Carts", icon="getcarts")


def _lay():
    """The app's Layer, which a handler's run owes a fill."""
    lay = uitree_app.env()
    lay.fill_owed = True
    return lay


class _Owed:
    """The app's damage: what owes a frame owes the page a fill too."""

    def __init__(self, damage, lay):
        self._d, self._lay = damage, lay

    def all(self):
        self._lay.fill_owed = True
        self._d.all()

    def again(self):
        self._lay.fill_owed = True
        self._d.again()

    def step(self):
        """A frame owed to the pump's work alone (a cover on its way): the
        page has not moved, so no fill, nothing made for one, and no window
        behind drawn again (`moved`)."""
        self._d.again()


def _set(lay, name, rows):
    """Model `name` written only where its rows moved."""
    if lay.models.get(name) != rows:
        lay.models[name] = rows
        setattr(s, name, rows)


def _lines(lay, name, pairs):
    _set(lay, name, [{"id": str(i), "text": t, "tone": tone} for i, (t, tone) in enumerate(pairs)])


def _view(lay):
    ph = lay.phase
    if lay.desk and lay._in_pane():
        return "desk"
    if ph == "list":
        return "shelf"
    if ph in ("cart", "done"):
        return "cart"
    if ph in ("getting", "consent"):
        return "getting"
    if ph in ("licence", "pick"):
        return ph
    return "busy" if ph in BUSY else "words"


def _fill_shelf(lay):
    rows = []
    for r in lay.rows:
        c = r["cart"]
        sh = lay._shown(r)
        rows.append({"id": c["folder"], "name": c["name"],
                     "sub": STATE_WORD.get(sh) or _mb(r["plan"]["store_bytes"]),
                     "icon": genre_icon(c), "pic": lay.cover_pic(c), "badge": BADGE.get(sh, ""),
                     "tone": "value" if sh == "update" else "danger" if sh in BLOCKED else ""})
    _set(lay, "carts", rows)
    s.none = not rows
    left, right = lay._caption()
    s.caption = left + (" · " + right if right else "")
    s.count, s.free = left, right


def _fill_cart(lay, row):
    c = row["cart"]
    s.name, s.icon, s.meta = c["name"], genre_icon(c), lay._meta(c)
    s.pic = lay.cover_pic(c)
    s.genre = _cl.genre_word(c.get("genre")) or ""
    s.src = c.get("shelf") or _host_of(c.get("index") or "")
    st = lay._state_line(row)
    text, icon, tone = st if st is not None else ("", "", "")
    s.state = text.split(":")[0] if lay.desk and tone == "value" else text
    s.state_icon, s.state_tone = icon, tone
    s.desc = c.get("description") or ""
    _set(lay, "facts", [{"id": str(i), "label": f[0], "value": f[1]}
                        for i, f in enumerate(lay._info(row, lay.desk))])
    s.get_ok = lay.blocker(row) is None
    s.play_ok = lay._inst.find(c["folder"]) is not None
    s.status = lay._status(row)


def _fill_work(lay):
    title, line, done, total = lay._progress_of()
    s.title, s.line, s.done, s.total, s.bar = title, line, done, total, bool(total)
    s.what = "Putting it on the shelf" if lay._shelving() else "Downloading"
    n = len(lay.indexes)
    s.counting = bool(lay.phase == "checking" and n and lay._step)
    if s.counting:
        step = max(0, min(lay._step - 1, n))
        s.step, s.steps, s.shelf = step, n, "Shelf %d of %d" % (min(step + 1, n), n)


def fill(lay):
    """The page's states from the app's phase; each model written only
    where its rows moved, so a settled page draws nothing."""
    ph = lay.phase
    if lay.desk and ph == "list" and lay.rows:
        f = lay.engine.focus_key
        lay._pane_follows(f.split("/")[0] if f else lay.rows[0]["cart"]["folder"])
        ph = lay.phase
    view = s.view = _view(lay)
    verbs = lay._current_verbs()
    for v in VERB:
        setattr(s, "v_" + vid(v), v in verbs)
    t = lay.toast
    s.toast, s.toast_icon = (t[0], t[1]) if t is not None else ("", "")
    if view in ("shelf", "desk"):
        _fill_shelf(lay)
    row = lay.cur if lay.cur is not None or view != "desk" or not lay.rows else lay.rows[0]
    s.shown = row is not None
    if row is not None and view in ("desk", "cart", "getting"):
        _fill_cart(lay, row)
    s.busy = ph in BUSY
    if view in ("desk", "getting", "busy"):
        _fill_work(lay)
    elif view == "words":
        icon, s.title, paras = lay._empty_words()
        s.words_icon = icon
        paras = list(paras[:3]) + [" ".join(paras[3:])] if len(paras) > 4 else list(paras) + [""] * (4 - len(paras))
        s.w0, s.w1, s.w2, s.w3 = paras
    elif view == "pick":
        s.title, pairs = lay._copy_words()
        _lines(lay, "lines", pairs)
    elif view == "licence":
        s.licence_name = lay.lic[0]["licence"].get("name") or "Its licence"
        s.licence = lay._lic_text
    s.asking = lay.asking and lay.cur is not None
    if s.asking:
        s.rm_title = "Remove %s?" % lay.cur["cart"]["name"]
    q = lay.question if ph == "consent" and lay.cur is not None else None
    s.consent = q is not None
    if q is None:
        s.password = ""
    else:
        s.q_title = "Install %s?" % lay.cur["cart"]["name"]
        _lines(lay, "perms", _perms.rows(q))
        s.gated = _pkg.gated(lay._inst, q)
        s.pw_line = _pkg.WRONG_PASSWORD if lay.password_bad else PASSWORD_LINE
        s.pw_tone = "danger" if lay.password_bad else "dim"
    f = lay._focus
    if f is not None:
        lay._focus = None
        if f != _NOWHERE:
            ui.focus(f)


def opened():
    fill(_lay())


def open_card(row):
    lay = _lay()
    lay._tap_row(lay.index(row.id))


def follow(row):
    """On the desk the pane shows the card focus moved to."""
    lay = uitree_app.env()
    if lay.desk and lay.phase in ("list", "cart", "done") and lay._pane_follows(row.id):
        lay.fill_owed = True


def _verb(verb):
    def press():
        _lay()._press(verb)
    return press


def back():
    _lay().back()


def remove():
    """Remove on the cart's page asks; Remove in its dialog removes."""
    lay = _lay()
    if lay.asking:
        lay._remove()
    else:
        lay._press("REMOVE")


def install():
    lay = _lay()
    lay.password = s.password
    lay._answer(True)
    s.password = lay.password


def check():
    _lay()._check()


ui.hook("opened", opened)
ui.action("open", "Open", open_card, takes="row")
ui.action("follow", "Show", follow, takes="row")
ui.action("get", "Get", _verb("GET"), when="get_ok", off="grey")
ui.action("update", "Update", _verb("UPDATE"), when="get_ok", off="grey")
ui.action("play", "Play", _verb("PLAY"), when="play_ok", off="grey")
ui.action("use", "Use", _verb("USE"), when="play_ok", off="grey")
ui.action("remove", "Remove", remove)
ui.action("agree", "I agree", _verb("I AGREE"))
ui.action("no", "No", back)
ui.action("cancel", "Cancel", back)
ui.action("ok", "OK", _verb("OK"))
ui.action("try_again", "Try again", _verb("TRY AGAIN"))
ui.action("wifi", "Wi-Fi", _verb("WIFI"))
ui.action("check", "Check", check, keys=("r",), when="view=shelf || view=desk", off="hide")
ui.action("install", "Install", install)


def _cards():
    with ui.cards("carts", cur="card", changed="follow", w="{@desk?128:64}", h="{@desk?128:64}",
                  pad="{@desk?8:12}"):
        ui.card("open", label="{.name}", sub="{.sub}", icon="{.icon}", tone="{.tone}", badge="{.badge}",
                image=".pic")
    ui.label("No carts on the shelf yet", tone="dim", shown="none")


def _facts():
    with ui.scroll("facts_view", shown="!busy"):
        with ui.group("", look="card"):
            with ui.rows("facts"):
                ui.info("{.label}", "{.value}")


def _verbs():
    """The cart's verbs, the one that goes on last the primary: Play (Use)
    beside Update is not."""
    ui.button("remove", "danger", icon="trash", shown="v_remove")
    ui.button("play", "{v_update?normal:primary}", icon="play", shown="v_play")
    ui.button("use", "{v_update?normal:primary}", icon="palette", shown="v_use")
    ui.button("update", "primary", icon="getcarts", shown="v_update")
    ui.button("get", "primary", icon="getcarts", shown="v_get")


def _toast():
    ui.toast("{toast}", icon="{toast_icon}", shown="toast")


def _shelf():
    with ui.row("caption", pad=16):
        ui.label("{count}", tone="dim", face="caption")
        ui.label("{free}", tone="dim", face="caption", align="end", shown="free")
    _cards()
    _toast()


def _desk():
    with ui.split("row", sizes=("1*", 274), pad=0, gap=8, rule=True):
        with ui.group(""):
            with ui.row("caption", pad=24):
                ui.label("{caption}", tone="dim", face="caption")
                ui.button("check", icon="rotate")
            _cards()
        with ui.group("", shown="shown"):
            with ui.row("head"):
                ui.picture(image="pic", icon="{icon}", side=128)
                with ui.group(""):
                    ui.label("{name}", face="title")
                    ui.label("{genre}", tone="dim", face="caption", shown="genre")
                    ui.label("{src}", tone="dim", face="caption", shown="src")
                    ui.label("{state}", icon="{state_icon}", tone="{state_tone}", wrap="word", lines=2,
                             shown="state && !busy")
            ui.label("{desc}", wrap="word", lines=3, shown="desc")
            _facts()
            ui.label("{title}", shown="busy")
            ui.progress("done", max="{total}", label="Downloading", shown="busy && bar")
            ui.label("{line}", tone="dim", face="caption", shown="busy")
    with ui.foot():
        ui.label("{status}", tone="dim", face="caption")
        _verbs()
        ui.button("cancel", "danger", icon="close", shown="v_cancel")
    _toast()


def _cart():
    with ui.row("head"):
        ui.picture(image="pic", icon="{icon}", side=64)
        with ui.group(""):
            ui.label("{meta}", tone="dim", face="caption")
            ui.label("{state}", icon="{state_icon}", tone="{state_tone}", wrap="word", lines=2, shown="state")
            ui.label("{desc}", wrap="word", lines=3, face="caption", shown="desc")
    _facts()
    with ui.foot(look="share"):
        _verbs()
    _toast()


def _getting():
    with ui.row("cover"):
        ui.picture(image="pic", icon="{icon}", side=64)
    ui.label("{title}", face="title", align="center")
    with ui.row("bar", pad=34):
        ui.progress("done", max="{total}", label="{what}")
    ui.label("{line}", tone="dim", face="caption", align="center", shown="line")
    with ui.row("verbs"):
        ui.button("cancel", "danger", icon="close", shown="v_cancel")


def _licence():
    ui.label("{licence_name}", face="title")
    ui.text_view("licence", face="ui", wrap="word", look="well")
    with ui.foot():
        ui.button("no")
        ui.button("agree", "primary")


def _pick():
    ui.label("{title}", face="title")
    with ui.rows("lines"):
        ui.label("{.text}", tone="{.tone}", wrap="word", lines=2)
    with ui.foot():
        ui.button("cancel", icon="close")


def _busy():
    with ui.empty("{title}", icon="getcarts", lines=["{line}"]):
        ui.progress("step", max="{steps}", label="{shelf}", shown="counting")
        with ui.row("verbs"):
            ui.button("cancel", icon="close")


def _words():
    with ui.empty("{title}", icon="{words_icon}", lines=["{w0}", "{w1}", "{w2}", "{w3}"]):
        with ui.row("verbs"):
            ui.button("try_again", "{v_wifi?normal:primary}", icon="rotate", shown="v_try_again")
            ui.button("wifi", "primary", icon="wifi", shown="v_wifi")
            ui.button("ok", "primary", shown="v_ok")


def build():
    with ui.page(""):
        ui.switch("view", {"shelf": _shelf, "desk": _desk, "cart": _cart, "getting": _getting,
                           "licence": _licence, "pick": _pick, "busy": _busy, "words": _words})
        with ui.dialog("{rm_title}", ["cancel", "remove"], kind="danger", shown="asking"):
            ui.label("Its saves and the files it wrote go too.", wrap="word", lines=3)
        with ui.dialog("{q_title}", ["no", "install"], shown="consent"):
            with ui.rows("perms"):
                ui.label("{.text}", tone="{.tone}", wrap="word", lines=3)
            ui.label("{pw_line}", tone="{pw_tone}", wrap="word", lines=2, shown="gated")
            ui.field("Password", "password", 64, secret=True, on="install", shown="gated", edit="open")


class GetCartsAppLayer(uitree_app.app_layer("getcarts", "Get Carts", build)):
    """The Get Carts Layer: the page's engine handed this layer as what its
    handlers reach (`uitree_app.env()`), and the index, the covers and the
    install it steps a slice a frame (`_pump`)."""

    TITLE = "Get carts"

    def __init__(self, ctx, names=None):
        super().__init__(ctx, names)
        self.engine.env = self
        self._inst = ctx.install
        self._nav = ctx.nav
        self._carts_role = ctx.carts
        self.names = names
        self.models = {}              # each model's rows as last written
        self.owed = False             # the last frame's press moved the page
        self.fill_owed = True         # the page's states owe a fill (`_Owed`, a handler's `_lay`)
        self._damage = _Owed(self._damage, self)
        self.phase = "list"
        self.carts = []               # every index's carts, this session
        self.rows = []                # [{"cart", "plan", "state", "had", "runs", "fit"}]
        self.fetched_at = None
        self.indexes = ()
        self.unreached = 0
        self.starved = False          # an index failed for want of memory
        self.no_addon = False         # an index lists browser consoles, none for this image
        self.free = None              # (bytes, block) of the store
        self.cur = None               # the CART page's row (the desk's pane)
        self.job = None
        self.lic = None               # [external]: the licence page's file
        self._lic_text = ""
        self.accepted = []
        self.asking = False           # Remove's dialog is up
        self.question = None          # the install prompt's lines, while it is up
        self._consented = None        # (app id, permissions, unreviewed) the install records
        self.password = ""            # typed into the prompt's password field (pkg.gated)
        self.password_bad = False     # the last one typed was not the console's
        self._revoked = {}            # parse_index's revocations, this check's indexes
        self._tail = None             # (steps, then, failed): a landing's or a removal's, a frame a step
        self._sweep = None            # what install/ holds going, a store op a frame, no key held
        self.why = ""                 # the NOT INSTALLED page's reason
        self.why_detail = None        # ...and its cause exact, under it
        self.toast = None             # (text, icon, until ms): a passing message
        self.thumbs = {}              # cover sha256 -> True once the engine holds it, False: failed
        self._covers = []             # the carts whose covers this check still fetches
        self._owed = {}               # ...their covers' sha256s, and those in flight
        self._jobs = []               # [(cart, its cover's fetch)] in flight
        self._here = {}               # a cart on the console: its folder -> its store path
        self._row_of = {}             # a cart's folder -> its card's place on the shelf
        self._tile = array("i", [0, 0, 0, 0])
        self._wait_gen = None         # the theme the "on its way" picture was put in
        self._found = []
        self._checking = None         # the check's steps (`_check_steps`), while it runs
        self._step = 0                # its place: 0 before the indexes, then 1 + the index it is on
        self._fetch = None            # the cart_index job in hand, and what it is
        self._fetching = None
        self.supplied = {}            # external path -> the player's own copy
        self._ext = 0                 # the external the probe or pick is on
        self._pick = None             # the page's file question, while it is up
        self._picked = []             # answered ones whose files the install reads
        self._filecheck = None        # the FileCheck of a picked file
        self.pick_why = None          # what was wrong with the last one
        self._held = False
        self._away = False            # the Wi-Fi page is open over the app
        self._focus = None            # the id focus moves to on the next frame
        self._board_free = None       # a Zero's page: the room the console reported

    # -- the app protocol (docs/app_api_v1.md) --------------------------------

    def open(self):
        self.asking = False
        self.job = None               # one the keeper still holds lands by itself
        self.lic = None
        self._away = False
        board = self._inst.board()
        if self._inst.home() is not None and board is None:
            self._go("board")
        elif board is None and self._inst.net() is None:
            self._go("nonet")
            self._focus = vid("TRY AGAIN")
        else:
            self._recover()
            self.cur = None           # a visit starts on the shelf's first card
            fresh = (self.fetched_at is not None
                     and _ticks_diff(_ticks_ms(), self.fetched_at) < REFRESH_MS)
            if self.carts and fresh:
                self._covers = self._covers_to_fetch(self.carts)
                self._build_rows()
                self._land()
            else:
                self._check()
        super().open()

    def close(self):
        job = self.job
        if job is not None and job.landing and not job.finished:
            consented, self._consented = self._consented, None
            _pkg.land_now(self._inst, job, consented)
        self._sweep = None            # what is left in install/ is the next open's recover
        self._end_tail()
        if self.job is not None and not self.job.finished and self.job.cancel():
            self._go("cart" if self.cur is not None else "list")
        self._drop_fetch()
        self._drop_covers()
        self._unpick()
        self._release()
        self._away = False
        super().close()

    def page_title(self):
        """The bar's title on a cart's own pages: the cart's name."""
        if self.cur is not None and not self.desk and (
                self.phase in ("cart", "done", "licence", "pick")
                or self.phase in BUSY and self.phase != "checking"):
            return self.cur["cart"]["name"]
        return None

    # -- the lease -----------------------------------------------------------------

    def _hold(self):
        if not self._held:
            self._held = True
            self._inst.hold()

    def _release(self):
        if self._held:
            self._held = False
            self._inst.release()

    # -- phases --------------------------------------------------------------------

    def _go(self, phase):
        self.phase = phase
        self.armed = False
        if phase == "nowifi":
            self._focus = vid("WIFI")
        elif phase in _AWAY:
            self._focus = vid("TRY AGAIN")
        elif phase == "failed":
            self._focus = vid("OK")
        elif phase in BUSY or phase == "pick":
            self._focus = _NOWHERE            # Cancel is B's or a tap's, never Enter's
        self._damage.all()

    def _land(self):
        """The shelf, the keys on the card `cur` names, else on the first:
        where an open and a check end. That card is `cur`, so the focus
        landing on it moves nothing: on the desk the pane shows it beside
        the shelf, and its page opens only when the player picks a card."""
        self._go("list")
        if self.rows:
            if self.cur is None:
                self.cur = self.rows[0]
            self._focus = self._card_id(self.cur)

    def _focus_go(self):
        """Focus on the cart's page's verb that goes on (the last)."""
        v = self._verbs()
        if v:
            self._focus = vid(v[-1])

    def _say(self, text, icon="check"):
        """A toast: `text` for TOAST_MS, or until the next key."""
        self.toast = (text, icon, _ticks_ms() + TOAST_MS)
        self._damage.all()

    def _check(self):
        self._drop_fetch()
        self._drop_covers()
        self._found = []
        self._covers = []
        self.unreached = 0
        self.starved = False
        self.no_addon = False
        self._checking = None
        self._step = 0
        self._go("checking")

    def _drop_fetch(self):
        job, self._fetch = self._fetch, None
        self._fetching = None
        if job is not None:
            job.close()

    def _fetched(self, start, what):
        """The fetch job `what` names, started by `start()` the first time and
        stepped after: its bytes once they are all in, else None (still on its
        way). Raises the job's InstallError, with the job let go."""
        if self._fetching != what:
            self._drop_fetch()
            self._fetch = start()
            self._fetching = what
        try:
            if self._fetch.step():
                return None
        except _ci.InstallError:
            self._drop_fetch()
            raise
        data = self._fetch.data
        self._fetch = None
        self._fetching = None
        return data

    def _recover(self):
        """What a cut or a closed app left in install/ finished, a sweep
        (`_step_sweep`) from the next frame; nothing when it holds nothing."""
        root = self._inst.root()
        if root is None or not self._inst.writable():
            return
        try:
            if not self._inst.op(lambda: _ci.staged(root)):
                return
        except Exception as exc:  # noqa: BLE001 -- recover runs again next open
            _ci._log("recover failed: %s" % exc)
            return
        self._sweep = _ci.stepped(self._inst.op, _ci.recover_steps(root))
        self._damage.again()

    def _drop(self):
        """A stopped install's build deleted over the next frames, a sweep
        (`_step_sweep`)."""
        if self.job is not None and self.job.dropping and not self.job.finished:
            self._sweep = _ci.drain(self.job)
            self._damage.again()

    def _step_sweep(self):
        """One store op of the sweep. It holds no key or tap: the pump's other
        work waits on it instead, so a new install never meets a build half
        deleted and a tap meanwhile still lands."""
        try:
            if next(self._sweep, _ci._DONE) is not _ci._DONE:
                self._damage.again()
                return
        except Exception as exc:  # noqa: BLE001 -- recover runs again next open
            _ci._log("install/ left for recover: %r" % (exc,))
        self._sweep = None
        self._damage.again()

    def _pump(self):
        """The BUSY phases' slice of work, one per drawn frame; between them
        the shelf's covers. A sweep of install/ goes first, then a landing's
        or a removal's steps, one a frame, holding every key until they end."""
        if self._sweep is not None:
            self._step_sweep()
            return
        if self._tail is not None:
            self._step_tail()
            return
        if self.phase == "pick":
            self._poll_pick()
        if self.phase not in BUSY:
            if (self._covers or self._jobs) and self.phase != "pick":
                self._pump_covers()
            return
        if self._jobs:
            self._drop_covers()
        if not self.armed:
            self.armed = True         # this frame shows the screen; work next frame
            self._damage.again()
            return
        try:
            ph = self.phase
            if ph == "checking":
                self._pump_check()
            elif ph == "licence_fetch":
                self._pump_licence()
            elif ph == "probing":
                self._pump_probe()
            elif ph == "picked":
                self._pump_picked()
            elif ph == "connecting":
                self._pump_connect()
            else:
                self._pump_get()
        except _ci.InstallError as exc:
            _ci._log(exc.detail)
            self._fail(exc.text, exc.detail)
        except Exception as exc:  # noqa: BLE001 -- the store never takes the shell down
            _ci._log("%r" % (exc,))
            self._fail(_ci.STOPPED)
        if self.phase in BUSY:
            self._damage.again()

    def _run(self, steps, then, failed):
        """`steps` (pkg's `landed` or `removed`) stepped a frame a step from
        the next frame, then `then()`; `failed(exc)` when one raises."""
        self._tail = (steps, then, failed)
        self._damage.again()

    def _step_tail(self):
        steps, then, failed = self._tail
        try:
            if next(steps, _ci._DONE) is not _ci._DONE:
                self._damage.again()
                return
        except Exception as exc:  # noqa: BLE001 -- the store never takes the shell down
            self._tail = None
            _ci._log("%r" % (exc,))
            failed(exc)
            self._damage.again()
            return
        self._tail = None
        then()
        self._damage.again()          # the work a tail held goes on next frame

    def _end_tail(self):
        """The steps in hand done at once: the app is closing."""
        while self._tail is not None:
            self._step_tail()

    def _online(self):
        """The lease taken and the link up: True; None while the saved
        network is still being joined (the pump asks again next frame, the
        frame never waits on it); False (lease let go) when the console could
        not get online."""
        self._hold()
        net = self._inst.net()
        ready = getattr(net, "ready", None)
        up = ready() if ready is not None else net.online()
        if up is None:
            return None
        if up:
            return True
        self._release()
        return False

    def _starved(self):
        """True when the transport says the console has no memory left for a
        connection -- the radio's driver and a TLS download take theirs from
        the same internal RAM, so a radio that will not come up can be that
        too, not a network the kid has to join."""
        return _ci.net_text(self._inst.net(), None) == _ci.NET_MEMORY

    def _pump_check(self):
        board = self._inst.board()
        if board is not None:
            self._pump_board_check(board)
            return
        if self._checking is None:
            self._checking = self._check_steps()
        try:
            if next(self._checking, _ci._DONE) is not _ci._DONE:
                return
        except Exception:
            self._checking = None
            raise
        self._checking = None

    def _check_steps(self):
        """The check, a piece a frame (CHECK_MS): the link, each index's
        fetch and parse, then the shelf's rows."""
        net = self._inst.net()
        while True:
            up = self._online()
            if up:
                break
            if up is False:
                self._go("nomemory" if self._starved() else "nowifi")
                return
            yield
        root = self._inst.root()
        if root is not None and self._inst.writable():
            self.indexes = self._inst.op(lambda: _ci.load_indexes(root, self._inst.own()))
        else:
            self.indexes = list(_ci.DEFAULT_INDEXES)
        yield
        for i, url in enumerate(self.indexes):
            self._step = i + 1
            try:
                while True:
                    data = self._fetched(lambda: _ci.index_fetch(net, url), ("index", i))
                    if data is not None:
                        break
                    yield
                got = []
                yield from _ci.parse_steps(data, url, got, self._inst.own(), self._revoked,
                                           budget_ms=CHECK_MS)
                data = None
                self.no_addon = self.no_addon or _ci.addon_unfit(got)
                self._found.extend(_ci.fitting(got))
            except _ci.InstallError as exc:
                self.unreached += 1
                self.starved = self.starved or exc.text == _ci.NET_MEMORY
                _ci._log(exc.detail)
            yield
        self._step = len(self.indexes) + 1
        if not self._found and self.unreached:
            self._release()
            self._go("nomemory" if self.starved else "unreached")
            return
        self.carts = self._found
        self._found = []
        revoked, self._revoked = self._revoked, {}
        self._mark_revoked(lambda: _pkg.revocations(self._inst, revoked))
        self.fetched_at = _ticks_ms()
        self._covers = self._covers_to_fetch(self.carts)
        if not self._covers:
            self._release()
        yield
        yield from self._rows_steps(CHECK_MS)
        yield                         # the shelf's first paint, a frame of its own
        self._land()
        if self.rows:
            self._focus = self._card_id(self.cur if self.cur in self.rows else self.rows[0])

    def _mark_revoked(self, mark):
        """The consent records of carts whose store revoked their version
        marked (`mark()`, pkg's `revocations` or `revoked_rows`), so they
        will not launch; a store that fails here never takes the shelf
        down."""
        try:
            mark()
        except Exception as exc:  # noqa: BLE001
            _ci._log("revocations: %r" % (exc,))

    def _pump_board_check(self, board):
        """The console's official carts, asked of it: its list as this
        page's shelf, and the room in its store."""
        if self._fetching != "board":
            self._drop_fetch()
            self._fetch = board.check()
            self._fetching = "board"
        job = self._fetch
        if job.step():
            return
        self._fetch = None
        self._fetching = None
        if job.error is not None:
            _ci._log("the console's carts: %s" % job.error)
            self._go("nomemory" if job.error == _ci.NET_MEMORY else "unreached")
            return
        doc = job.doc
        free = doc.get("free")
        self._board_free = (free[0], free[1]) if isinstance(free, list) and len(free) == 2 \
            else None
        self.indexes = ()
        self.carts = [c for c in doc.get("carts") or ()
                      if isinstance(c, dict) and isinstance(c.get("assets"), list)]
        self.unreached = doc.get("unreached") or 0
        self.fetched_at = _ticks_ms()
        self._covers = self._covers_to_fetch(self.carts)
        self._build_rows()
        self._mark_revoked(lambda: _pkg.revoked_rows(self._inst, self.rows))
        self._go("list")
        if self.rows:
            self._focus = self._card_id(self.cur if self.cur in self.rows else self.rows[0])

    def _pump_covers(self):
        """The shelf's covers, fetched after it shows rather than before:
        COVERS_AHEAD asked of the http worker at once, the card in view
        first, each stepped every drawn frame while any is owed and drawn
        from the frame it lands in. On a Zero's page a cover is the copy of
        a cart the console holds, one read a frame."""
        self._put_wait()
        if self._inst.board() is not None:
            cart = self._next_cover()
            try:
                self._local_cover(cart)
            except Exception as exc:  # noqa: BLE001 -- a cover never takes the shelf down
                _ci._log("%r" % (exc,))
            self._cover_done(cart, False)
            if self._covers:
                self._damage.step()
            return
        self._hold()
        jobs = self._jobs
        while self._covers and len(jobs) < COVERS_AHEAD:
            cart = self._next_cover()
            try:
                jobs.append((cart, _ci.cover_fetch(self._inst.net(), cart)))
            except _ci.InstallError as exc:
                _ci._log(exc.detail)
                self._cover_done(cart, None)
        i = 0
        while i < len(jobs):
            cart, job = jobs[i]
            try:
                if job.step():
                    i += 1
                    continue
                data = job.data
            except Exception as exc:  # noqa: BLE001 -- a cover never takes the shelf down
                _ci._log(getattr(exc, "detail", None) or "%r" % (exc,))
                data = None
            jobs.pop(i)
            self._cover_done(cart, data)
        if self._covers or jobs:
            self._damage.step()
        else:
            self._release()

    def _next_cover(self):
        """The owed cover the shelf shows first: the top card's in view,
        else the top card's."""
        covers = self._covers
        cells = getattr(self.engine, "cells_tile", None)
        best = top = None
        n = len(self._row_of)
        for i in range(len(covers)):
            at = self._row_of.get(covers[i]["folder"], n)
            if top is None or at < top[0]:
                top = (at, i)
            if cells is not None and at < n and cells(at, self._tile) and (best is None or at < best[0]):
                best = (at, i)
        return covers.pop((best or top)[1])

    def _cover_done(self, cart, data):
        """`cart`'s cover come (`data` its bytes), failed (None) or read
        here (False): the card shows it, or its icon."""
        sha = cart["cover"]["sha256"]
        self._owed.pop(sha, None)
        if data:
            self._decode_cover(cart, data)
        elif data is None:
            self.thumbs[sha] = False
        self._damage.all()

    def _drop_covers(self):
        """The fetches in flight let go, their carts owed again first."""
        jobs, self._jobs = self._jobs, []
        for cart, job in jobs:
            job.close()
        self._covers[:0] = [cart for cart, _job in jobs]

    def _covers_to_fetch(self, carts):
        """The carts whose covers are fetched: those not on the console, one
        a cover, whose cover the engine does not hold yet."""
        self._find_here()
        out = []
        owed = {}
        flying = {cart["cover"]["sha256"]: True for cart, _job in self._jobs}
        board = self._inst.board() is not None
        root = self._inst.root()
        for c in carts:
            ref = c.get("cover")
            if ref is None or c["folder"] in self._here:
                continue
            sha = ref["sha256"]
            if sha in owed or sha in flying:
                continue
            if board and (root is None or not moy_store.exists("%s/%s/cover.png" % (root, c["folder"]))):
                continue
            if not self.thumbs.get(sha):
                out.append(c)
                owed[sha] = True
        owed.update(flying)
        self._owed = owed
        return out

    def _find_here(self):
        """Which of the shelf's carts are on the console (`_here`)."""
        root = self._inst.root()
        if self._inst.board() is not None or root is None:
            self._here = {}
            return
        paths = {}
        for c in self._carts_role.all():
            p = c.get("path")
            if p:
                paths[p] = True
        here = {}
        for c in self.carts:
            p = "%s/%s" % (root, c["folder"])
            if p in paths:
                here[c["folder"]] = p
        self._here = here

    def _local_cover(self, cart):
        """One cover read from the cart's copy here and decoded."""
        path = "%s/%s/cover.png" % (self._inst.root(), cart["folder"])

        def _bytes():
            with open(path, "rb") as f:
                return f.read()
        try:
            data = self._inst.op(_bytes)
        except OSError:
            return
        self._decode_cover(cart, data)

    def cover_pic(self, cart):
        """The picture a card and the cart's page show for `cart`: a cart on
        the console its copy's cover, from the shell's cover cache; another
        its fetched cover once the engine holds it, the "on its way"
        picture while it is owed, else None (its genre's icon)."""
        path = self._here.get(cart["folder"])
        if path is not None:
            return ui.image.cart(path)
        ref = cart.get("cover")
        if ref is None:
            return None
        sha = ref["sha256"]
        if self.thumbs.get(sha):
            return ui.image.own("cover:" + sha)
        if sha in self._owed:
            return ui.image.own(WAIT)
        return None

    def _put_wait(self):
        """The "on its way" picture put, again where the theme moved."""
        gen = self._theme.gen()
        if gen == self._wait_gen:
            return
        self._wait_gen = gen
        render = _wait_render(self)
        self.engine.run(lambda: ui.pictures.put(WAIT, render=render, clear=True))

    def _decode_cover(self, cart, data):
        """A cover's bytes handed to the engine, which decodes them where a
        card draws its picture (the idle step's work, run as the app's)."""
        sha = cart["cover"]["sha256"]
        self.engine.run(lambda: ui.pictures.put("cover:" + sha, data=data))
        self.thumbs[sha] = True

    def _build_rows(self):
        for _ in self._rows_steps(None):
            pass

    def _rows_steps(self, budget_ms):
        """`rows` made from `carts`, yielding each time `budget_ms` has
        passed in the store's scan (None: not there)."""
        inst = self._inst
        root = inst.root()
        chip, fmt = inst.chip()
        have = inst.runtimes()
        ranges = bool(getattr(inst.net(), "ranges", False))
        carts = self.carts
        board = inst.board()

        def _row(c, rec):
            p = _ci.plan(c, chip, fmt, ranges)
            if board is not None:           # where it stands is the board's store's
                return {"cart": c, "plan": p, "state": c.get("state") or "get",
                        "had": c.get("had"), "runs": _ci.runs_on(c, have), "fit": None}
            folder = "%s/%s" % (root, c["folder"])
            present = root is not None and moy_store.exists(folder)
            entry = rec.get(c["folder"])
            man = None
            if present and (entry is None or entry.get("id") != c["id"]
                            or _ci.is_official(c)):
                try:
                    man = json.loads(moy_store.read(folder + "/manifest.json"))
                except (OSError, ValueError):
                    man = None
            return {"cart": c, "plan": p,
                    "state": _ci.cart_state(c, p, entry, present, man),
                    "had": entry.get("version") if entry is not None else None,
                    "runs": _ci.runs_on(c, have), "fit": None}
        try:
            rec = inst.op(lambda: _ci.load_record(root)) \
                if board is None and root is not None else {}
            rows = []
            t = _ticks_ms()
            for c in carts:                 # a store op a cart
                if budget_ms is not None and _ticks_diff(_ticks_ms(), t) >= budget_ms:
                    yield
                    t = _ticks_ms()
                rows.append(inst.op(lambda: _row(c, rec)))
            if budget_ms is not None:
                yield                       # the store's room and the fits, a frame of their own
            if board is not None:
                free = self._board_free
            else:
                free = inst.op(inst.free) if root is not None else None
        except Exception as exc:  # noqa: BLE001 -- an unreadable store lists everything as GET
            _ci._log("store scan failed: %s" % exc)
            rows = [{"cart": c, "plan": _ci.plan(c, chip, fmt, ranges), "state": "get",
                     "had": None, "runs": False, "fit": None} for c in carts]
            free = None
        self._find_here()
        have = _pkg.installed_ids(self._carts_role.all())
        for r in rows:
            c = r["cart"]
            r["fit"] = (_pkg.fit_why(self._inst, c, r["plan"])
                        or _pkg.depends_why(carts, c, have))
        rows.sort(key=lambda r: r["cart"]["name"].lower())
        self.rows = rows
        self._row_of = {r["cart"]["folder"]: i for i, r in enumerate(rows)}
        self.free = free
        if self.cur is not None:
            folder = self.cur["cart"]["folder"]
            ident = self.cur["cart"]["id"]
            self.cur = None
            for r in rows:
                if r["cart"]["folder"] == folder and r["cart"]["id"] == ident:
                    self.cur = r

    # -- the CART screen's verbs ---------------------------------------------------

    def _tap_row(self, i):
        """A card opened: its page, focus on the verb that goes on (on the
        desk the pane is that page, its verbs in the foot)."""
        if 0 <= i < len(self.rows):
            self.cur = self.rows[i]
            self.asking = False
            self._go("cart")
            self._focus_go()

    def _go_verb(self):
        """PLAY, or USE for a theme package: what an installed cart does."""
        cur = self.cur
        return "USE" if cur is not None and cur["cart"]["runtime"] == "theme" else "PLAY"

    def _verbs(self):
        """The cart page's verbs; a core cart (moy_seed.CORE) has no Remove."""
        st = self.cur["state"] if self.cur is not None else None
        if st == "get":
            return ("GET",)
        rm = () if _store.is_core(self.cur["cart"]["folder"]) else ("REMOVE",)
        if st == "installed":
            return rm + (self._go_verb(),)
        if st == "update":
            return rm + (self._go_verb(), "UPDATE")
        if st == "revoked":
            return rm
        return ()

    def blocker(self, row):
        """Why `row` cannot be installed here, or None (pkg.blocker)."""
        return _pkg.blocker(self._inst, row["cart"], row["plan"], self.free,
                            row["runs"], row.get("fit"))

    def _press(self, verb):
        ph = self.phase
        if ph in ("cart", "done"):
            if verb in ("GET", "UPDATE"):
                self._start()
            elif verb == "PLAY":
                self._play()
            elif verb == "USE":
                self._use()
            elif verb == "REMOVE":
                self.asking = True
                self._damage.all()
        elif ph == "licence":
            if verb == "I AGREE":
                self.accepted.append(self.lic[0]["path"])
                self._next_licence()
            else:
                self._release()
                self._say("Not fetched")
                self._go("cart")
                self._focus_go()
        elif ph in BUSY or ph == "pick":
            self._cancel()
        elif verb == "WIFI":
            self._away = True
            self._inst.wifi()
        elif ph == "nonet":
            self.open()
        elif ph in _AWAY:
            self._check()
        elif ph == "failed":
            self._go("cart" if self.cur is not None else "list")
            if self.cur is not None:
                self._focus_go()

    def _start(self):
        if self.blocker(self.cur) is not None:
            return
        self.accepted = []
        self.supplied = {}
        self.pick_why = None
        self.asking = False
        self._next_licence()

    def _next_licence(self):
        for e in self.cur["plan"]["external"]:
            if e["path"] not in self.accepted:
                self.lic = [e]
                self._go("licence_fetch")
                return
        self.lic = None
        self._ext = 0
        if self._inst.can_pick() and self.cur["plan"]["external"]:
            self._go("probing")
        else:
            self._go("connecting")

    def _pump_licence(self):
        board = self._inst.board()
        if board is not None:
            self._pump_board_licence(board)
            return
        up = self._online()
        if up is None:
            return
        if not up:
            self._fail(_ci.NET_MEMORY if self._starved() else "WiFi isn't connected.")
            return
        ext = self.lic[0]
        net = self._inst.net()
        cart = self.cur["cart"]
        data = self._fetched(lambda: _ci.licence_fetch(net, cart, ext["licence"]),
                             ("licence", ext["path"]))
        if data is None:
            return
        self._lic_text = _ci.as_text(data)
        self._go("licence")
        self._focus = vid("NO")             # No has the focus

    def _pump_board_licence(self, board):
        """The licence asked of the console with no screen, which fetches
        and checks it as this console would."""
        ext = self.lic[0]
        what = ("licence", ext["path"])
        if self._fetching != what:
            self._drop_fetch()
            self._fetch = board.licence(self.cur["cart"], ext["path"])
            self._fetching = what
        job = self._fetch
        if job.step():
            return
        self._fetch = None
        self._fetching = None
        if job.error is not None:
            self._fail(job.error, getattr(job, "detail", None))
            return
        self._lic_text = str(job.doc.get("text") or "")
        self._go("licence")
        self._focus = vid("NO")

    # -- YOUR COPY: an external file this console cannot fetch -----------------

    def _external(self):
        ext = self.cur["plan"]["external"]
        return ext[self._ext] if self._ext < len(ext) else None

    def _next_external(self):
        self._ext += 1
        self.pick_why = None
        if self._external() is None:
            self._go("connecting")
        else:
            self._go("probing")

    def _pump_probe(self):
        """Can this console read the external file from its mirror or any of
        its archive's hosts? Yes: the install fetches it. No: the player picks
        a copy."""
        e = self._external()
        if e is None:
            self._go("connecting")
            return
        up = self._online()
        if up is None:
            return
        if not up:
            self._fail("WiFi isn't connected.")
            return
        if self._fetching != ("reach", self._ext):
            self._drop_fetch()
            net = self._inst.net()
            index = self.cur["cart"]["index"]
            self._fetch = _ci.Reach(net, [_ci.resolve(index, u)
                                          for u in _ci.external_sources(e)])
            self._fetching = ("reach", self._ext)
        if self._fetch.step():
            return
        reach, self._fetch, self._fetching = self._fetch, None, None
        if reach.url is not None:
            self._next_external()
            return
        _ci._log("%s: no host this console can read (%s)"
                 % (e["path"], "; ".join(reach.why)))
        self._ask_pick()

    def _ask_pick(self):
        e = self._external()
        if self._pick is not None:
            self._pick.close()        # a question answered with the wrong file
        self._pick = self._inst.pick(e["path"], e["size"],
                                     _ext_host(self.cur["cart"], e))
        if self._pick is None:
            self._fail(_ci.UNREACHABLE)
            return
        self._go("pick")

    def _poll_pick(self):
        got = self._pick.poll() if self._pick is not None else None
        if got is None:
            return
        if got[0] != "file":
            self._unpick()
            self._release()
            self._say("Not fetched")
            self._go("cart")
            self._focus_go()
            return
        e = self._external()
        self._filecheck = _ci.FileCheck(got[1], e["size"], e["sha256"])
        self._go("picked")

    def _pump_picked(self):
        """The picked file held to the index, a slice a frame."""
        chk = self._filecheck
        if chk.step():
            return
        self._filecheck = None
        e = self._external()
        if chk.why is None:
            self.supplied[e["path"]] = chk.path
            self._picked.append(self._pick)
            self._pick = None
            self._next_external()
            return
        self.pick_why = "That isn't %s: %s." % (e["path"], chk.why)
        self._ask_pick()

    def _unpick(self):
        """Every question to the player goes, and the files they answered with:
        the install has read them, or will not."""
        p, self._pick = self._pick, None
        done, self._picked = self._picked, []
        for q in [p] + done:
            if q is not None:
                q.close()
        chk, self._filecheck = self._filecheck, None
        if chk is not None:
            chk.close()

    def _pump_connect(self):
        board = self._inst.board()
        if board is not None:
            self.job = board.install(self.cur["cart"], self.accepted, self._ask_board)
            self._go("getting")
            self.armed = True
            return
        up = self._online()
        if up is None:
            return
        if not up:
            self._fail(_ci.NET_MEMORY if self._starved() else "WiFi isn't connected.")
            return
        row = self.cur
        arc = 0
        for e in row["plan"]["external"]:
            arc += e["archive"]["size"]
        mem = self._inst.memory()
        keep = "store" if (arc and mem is not None
                           and mem[1] < ARCHIVE_RAM_SHARE * arc) else "ram"
        self.job = _ci.Install(row["cart"], row["plan"], self._inst.net(),
                               self._inst.root(), self._inst.op, self.accepted,
                               archive=keep, supplied=self.supplied,
                               keep=self._inst.keep(), ask=self._ask)
        self._go("getting")
        self.armed = True

    def _ask(self, stage):
        """The install check and prompt for the checked build at `stage`
        (`cart_index.Install`'s `ask`): the prompt's lines, or None to go
        on. A permission the cart requires that this console lacks refuses
        the install."""
        c = self.cur["cart"]
        aid, perms, lines, src = _pkg.install_check(self._inst, stage, c["folder"],
                                                    self._carts_role.all(), c)
        self._consented = (aid, perms, src)
        return lines

    def _ask_board(self, man):
        """`_ask` over the manifest of the build a console with no screen
        checked (carts_link.BoardAsk's `ask`)."""
        c = self.cur["cart"]
        aid, perms, lines, src = _pkg.manifest_check(self._inst, man, c["folder"],
                                                     self._carts_role.all(), c)
        self._consented = (aid, perms, src)
        return lines

    def _pump_get(self):
        job = self.job
        if job.step():
            if job.asking is not None and self.question is None:
                self.question = job.asking
                self.password = ""
                self.password_bad = False
                self._release()           # nothing left to fetch
                self._go("consent")
            return
        self._release()
        self._unpick()
        if job.path and self._inst.board() is not None:
            consented, self._consented = self._consented, None   # the console landed it
            self.cur["cart"]["state"] = "installed"
            self.cur["cart"]["had"] = self.cur["cart"]["version"]
            self._run(_pkg.consent_steps(self._inst, consented), self._got,
                      lambda exc: self._fail(_ci.STOPPED))
        elif job.path:
            consented, self._consented = self._consented, None
            self._run(_pkg.landed(self._inst, job.path, consented), self._got,
                      lambda exc: self._fail(_ci.STOPPED))
        elif job.error:
            self._fail(job.error, getattr(job, "detail", None))
        else:
            self._go("cart")
            self._focus_go()

    def _got(self):
        if self._inst.board() is not None:
            self._covers = self._covers_to_fetch(self.carts)
        self._build_rows()
        self._go("done")
        self._say("%s is on your shelf" % self.cur["cart"]["name"])
        self._focus = vid(self._go_verb())

    def _cancel(self):
        """B, or a tap on CANCEL -- never A, which a kid presses at anything.
        Not once the keeper has the build: it lands."""
        checking = self.phase == "checking"
        if self.job is not None and not self.job.finished and not self.job.cancel():
            return
        self._drop()
        self._drop_fetch()
        self._unpick()
        self._release()
        self._say("Stopped" if checking else "Stopped. Nothing changed.")
        self._go("cart" if self.cur is not None and not checking else "list")
        if self.phase == "cart":
            self._focus_go()

    def _fail(self, why, detail=None):
        """The NOT INSTALLED page: `why` in a kid's words, `detail` the
        cause exact, its Details line, where it says more."""
        self._drop_fetch()
        self._unpick()
        self._release()
        self.why = why
        self.why_detail = detail if detail and detail != why else None
        self._go("failed")

    def _play(self):
        cart = self._inst.find(self.cur["cart"]["folder"])
        if cart is None:
            return
        self._release()
        self._nav.play(cart)

    def _use(self):
        """Make the installed theme package the console's theme: its name is
        its folder's stem."""
        folder = self.cur["cart"]["folder"]
        if self._inst.find(folder) is None:
            return
        name = folder[:-4] if folder.endswith(".moy") else folder
        self._theme.set(name)
        self._say("Using " + self.cur["cart"]["name"])
        self._damage.all()

    def _answer(self, install):
        """The install prompt answered: Install puts the build on the shelf,
        No removes it. Where the prompt carries the unreviewed warning and
        the console has a password (pkg.gated), Install takes it: one typed
        wrong keeps the prompt up, saying so; a console with no screen
        checks it itself, with its yes."""
        job = self.job
        if install and _pkg.gated(self._inst, self.question):
            pw = self.password
            if self._inst.board() is not None:
                self.question = None
                job.agree(pw)
                self._go("getting")
                self.armed = True
                return
            if not (pw and self._inst.unlock(pw)):
                self.password = ""
                self.password_bad = True
                self._damage.all()
                return
        self.question = None
        self.password = ""
        if install:
            job.agree()
            self._go("getting")
            self.armed = True
            return
        self._consented = None
        job.cancel()
        self._drop()
        self._unpick()
        self._say("Not installed. Nothing changed.")
        self._go("cart")
        self._focus_go()

    def _remove(self):
        """The cart off the shelf, its saves and the files it wrote with it:
        what Remove's dialog said; and the consent it was installed with."""
        self.asking = False
        row = self.cur
        board = self._inst.board()
        steps = self._board_removed(board, row) if board is not None \
            else _pkg.removed(self._inst, row["cart"]["folder"])
        self._run(steps, lambda: self._removed(row), self._not_removed)

    def _board_removed(self, board, row):
        """`yield from` it: the console with no screen takes the cart off its
        store, and the consent it was installed with is forgotten here."""
        had = self._inst.find(row["cart"]["folder"])
        yield from _asked(board.remove(row["cart"]["folder"]))
        row["cart"]["state"] = "get"
        row["cart"]["had"] = None
        if had is not None:
            yield from self._inst.consent().forget_steps(_perms.app_id(had))

    def _removed(self, row):
        self._build_rows()
        self.cur = None
        self._say("Removed " + row["cart"]["name"])
        self._go("list")
        self._focus = self._card_id(row)

    def _not_removed(self, exc):
        self._say("Can't remove it", "warn")
        self._damage.all()

    def has_page(self):
        """Whether a page of the app is open, which `back` steps out of: a
        licence, a fetch or a pick, a cart's page, Remove's dialog."""
        if self.desk and self._in_pane():
            return self.asking        # the pane is the shelf's: no page to leave
        return self._paged()

    def _paged(self):
        ph = self.phase
        return self.asking or ph in _PAGES or ph in BUSY

    def _in_pane(self):
        """Whether the desk shows this phase in the pane beside the shelf."""
        ph = self.phase
        return ph in ("list", "cart", "done", "getting", "consent") or (
            ph in BUSY and self.cur is not None and ph != "checking")

    def back(self):
        """Back one level (B, Esc, the bar's chevron): Remove's dialog closes,
        a licence is declined, a fetch or a pick cancelled, a cart's page goes
        back to the shelf. False on the shelf: the host leaves the app."""
        if self._tail is not None:
            return True
        if not self._paged() or self.desk and self.phase in ("cart", "done") \
                and not self.asking:
            return False
        ph = self.phase
        if self.asking:
            self.asking = False
            self._focus = vid("REMOVE")
        elif ph == "consent":
            self._answer(False)
        elif ph == "licence":
            self._press("NO")
        elif ph in BUSY or ph == "pick":
            self._cancel()
        else:
            row = self.cur
            self._go("list")
            if row is not None:
                self._focus = self._card_id(row)
        self._damage.all()
        return True

    # -- input -----------------------------------------------------------------

    def _current_verbs(self):
        """The page's verbs, left to right, the one that goes on last."""
        ph = self.phase
        if ph in ("cart", "done"):
            return self._verbs()
        if ph == "licence":
            return ("NO", "I AGREE")
        if ph == "getting" and self._shelving():
            return ()
        if ph in BUSY or ph == "pick":
            return ("CANCEL",)
        if ph == "nowifi":
            return ("TRY AGAIN", "WIFI")
        if ph in _AWAY:
            return ("TRY AGAIN",)
        if ph == "failed":
            return ("OK",)
        return ()

    def handle_input(self, inp):
        if self._tail is not None:
            return True
        if self.toast is not None and (getattr(inp, "typed", 0) or _any_key(inp)):
            self.toast = None
            self._damage.all()
        if self.phase in BUSY or self.phase == "pick":
            # A kid presses A at anything, and twice after Get: while work is
            # in hand only B (Esc) or a tap on Cancel stops it
            if inp.pressed("b"):
                self.back()
            return True
        if inp.pressed("b"):
            self.back()
            return True
        return self.engine.keys(inp)

    def handle_pointer(self, px, py, click):
        if self._tail is not None:
            return True
        return self.engine.point(px, py, click)

    # -- the frame -----------------------------------------------------------------

    def draw(self, dt):
        self.engine.band = not self.desk      # a desk's window shows no hints band, as it never did
        self._pump()
        if self._away and not self._inst.wifi_open():
            self._away = False            # back from the Wi-Fi page: look again
            if self.phase in _AWAY:
                self._check()
        elif self._away:
            self._damage.again()          # watch for the page to close
        if self.toast is not None:
            if _ticks_diff(_ticks_ms(), self.toast[2]) >= 0:
                self.toast = None
                self.fill_owed = True
            else:
                self._damage.again()
        if self.fill_owed:
            self.fill_owed = False
            self.engine.run(fill, self, action="fill")
            ui.commit(self.engine)
        super().draw(dt)
        self.owed = self.fill_owed        # a press in the frame moved the page: the next frame shows it

    def moved(self):
        return self.owed or super().moved()

    def do(self, fn, *args):
        """`fn(*args)` run as the page's handler, then the page filled, one
        commit."""
        self.engine.run(fn, *args, action="console")
        self.engine.run(fill, self, action="fill")
        ui.commit(self.engine)
        self._damage.all()

    def state(self):
        """The page's state, this engine's values."""
        self.engine._bind()
        return s

    # -- the shelf ---------------------------------------------------------------

    def _card_id(self, row):
        """Row `row`'s card's stop."""
        return row["cart"]["folder"] + "/open"

    def index(self, folder):
        """The row of the cart in `folder`, or -1."""
        for i in range(len(self.rows)):
            if self.rows[i]["cart"]["folder"] == folder:
                return i
        return -1

    def _shown(self, row):
        """Where a card stands as it says it: a cart only for the getting
        or the updating that needs a newer firmware is Needs update, one only
        for the getting that this console cannot take Too big or Can't play."""
        st = row["state"]
        if st in ("get", "update") and _ci.newer_why(row["cart"]) is not None:
            return "newer"
        if st == "get" and not row["runs"]:
            return "noplay"
        if st == "get" and (row["fit"] or self._no_room(row)):
            return "too_big"
        return st

    def _no_room(self, row):
        if self.free is None:
            return False
        return _ci.need_bytes(row["plan"], self.free[1]) > self.free[0]

    def _caption(self):
        n = len(self.rows)
        left = "%d cart%s" % (n, "" if n == 1 else "s")
        if self.unreached:
            left += " · %d shelf away" % self.unreached
        if self.no_addon:
            left += " · " + NO_ADDON
        right = "%s free" % _mb(self.free[0]) if self.free is not None else ""
        return left, right

    def _pane_follows(self, folder):
        """On the desk the pane shows the card focus is on, the one in
        `folder`: whether it moved to another."""
        for row in self.rows:
            if row["cart"]["folder"] == folder and row is not self.cur:
                self.cur = row
                if self.phase == "list" or self.phase == "done":
                    self.phase = "cart"
                return True
        return False

    # -- a cart's page -----------------------------------------------------------

    def _meta(self, c):
        dot = " · "
        word = _cl.genre_word(c.get("genre"))
        src = c.get("shelf") or _host_of(c.get("index") or "")
        return dot.join([p for p in (word, src) if p])

    def _state_line(self, row):
        """(text, icon, tone) of where the cart stands, or None."""
        c = row["cart"]
        st = row["state"]
        arrow = " → "
        if st in ("get", "update"):
            newer = _ci.newer_why(c)
            if newer is not None:
                return (newer, "warn", "danger")
        if st == "update":
            if row.get("had"):
                return ("Update ready: %s%s%s" % (row["had"], arrow, c["version"]),
                        "getcarts", "value")
            return ("Update ready", "getcarts", "value")
        if st == "installed":
            return ("On console", "check", "value")
        if st == "taken":
            return ("Another cart here is already called %s." % c["folder"], "warn",
                    "danger")
        if st == "revoked":
            return ("Its store took this cart back. It won't run: remove it.", "warn",
                    "danger")
        why = self.blocker(row) if st == "get" else None
        if why:
            return (why, "warn", "danger")
        return None

    def _info(self, row, desk):
        c, p = row["cart"], row["plan"]
        lic = c["licence"]
        out = [("Licence", lic.get("spdx") or lic.get("name") or "?")]
        dot = " · "
        arrow = " → "
        if desk:
            if row["state"] == "update" and row.get("had"):
                out.append(("Version", "%s%s%s" % (row["had"], arrow, c["version"])))
            out.append(("Takes", _mb(p["store_bytes"]) + " here"))
            out.append(("Fetch", _mb(p["download_bytes"])))
        else:
            out.append(("Size", "%s here%s%s to fetch" % (_mb(p["store_bytes"]), dot,
                                                          _mb(p["download_bytes"]))))
        home = _host_of(c.get("index") or "")
        out.append(("From", home))
        for e in p["external"]:
            # a file from the cart's own host names no host: the From row says it
            there = _ext_host(c, e)
            out.append(("Needs", e["path"] if there == home else "%s from %s" % (e["path"], there)))
        if p["slow"]:
            out.append(("Plays slowly on this console", ""))
        return out

    # -- the desk's pane and foot ------------------------------------------------

    def _status(self, row):
        dot = " · "
        if self.phase in BUSY:
            return self._progress_of()[0]
        st = self._shown(row)
        word = STATE_WORD.get(st)
        name = row["cart"]["name"]
        return name + dot + word[0].lower() + word[1:] if word else name

    # -- the getting -------------------------------------------------------------

    def _progress_of(self):
        """(title, line, done, total) of the work in hand."""
        name = self.cur["cart"]["name"] if self.cur is not None else ""
        job = self.job
        if self.phase == "consent":
            return ("Getting " + name, "", 1, 1)  # every byte in and checked
        if self.phase == "getting" and job is not None:
            if self._shelving():
                return ("Getting " + name, "Putting it on the shelf…", job.total, job.total)
            dot = " · "
            line = "%s of %s" % (_mb(job.done), _mb(job.total))
            rate = job.rate()
            if rate:
                line += "%s%d KB/s" % (dot, rate // 1024)
            return ("Getting " + name, line, job.done, job.total)
        title, line = self._busy_words()
        return (title, line, 0, 0)

    def _shelving(self):
        """Every byte is in and checked, and the cart is moving onto the
        shelf: the keeper has it, or its landing's steps are under way."""
        job = self.job
        return job is not None and (job.keeping or job.landing)

    # -- the pages that are words and a verb -------------------------------------

    def _busy_words(self):
        ph = self.phase
        if ph == "checking":
            return ("Checking", "Looking for carts…")
        if ph == "licence_fetch":
            return ("One moment", "Getting the licence…")
        if ph == "probing":
            e = self._external()
            return ("One moment", "Looking for %s…" % (e["path"] if e else "it"))
        if ph == "picked":
            return ("Your copy", "Checking your copy…")
        if ph == "connecting":
            if self._inst.board() is not None:
                return ("Connecting", "Asking the console…")
            return ("Connecting", "Turning on Wi-Fi…")
        return ("", "")

    def _empty_words(self):
        """(icon, title, lines) for the pages that say why there is no
        shelf, or how a getting ended."""
        ph = self.phase
        if ph == "board":
            lines = ["This page shows the carts kept on the console that served it."]
            if self._inst.home() == "headless":
                lines.append("Update this console to get carts from here.")
            else:
                lines.append("Get new carts on the console itself: turn Web console off "
                             "there and open Get Carts.")
            return ("getcarts", "On the console", lines)
        if ph == "nonet":
            return ("warn", "No internet", ["This console has no way to fetch carts."])
        if ph == "nowifi":
            return ("wifi_off", "Wi-Fi is off", ["Join a network and Get Carts",
                                                 "looks again by itself."])
        if ph == "unreached":
            return ("warn", "Shelf away", ["Couldn't reach the cart shelf.",
                                           "Try again soon."])
        if ph == "nomemory":
            return ("warn", "Memory full", [_ci.NET_MEMORY])
        if ph == "failed":
            lines = [self.why, "Nothing changed."]
            if self.why_detail:
                lines.append("Details: " + self.why_detail)
            return ("warn", "Not installed", lines)
        return ("getcarts", "", [])

    def _copy_words(self):
        """(title, [(line, tone)]) of YOUR COPY's page."""
        e = self._external()
        lines = []
        if self.pick_why is not None:
            lines.append((self.pick_why, "danger"))
        lines.append(("This console can't fetch %s from %s."
                      % (e["path"], _ext_host(self.cur["cart"], e)), "ink"))
        lines.append(("Choose your own copy of %s (%s) from this computer."
                      % (e["path"], _mb(e["size"])), "dim"))
        return "Your copy of %s" % e["path"], lines
