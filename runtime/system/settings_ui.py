"""Settings' pages written as `uitree` builds, which `SettingsLayer` hosts
in its sub page's frame (`SettingsPages`):

- Time zone: the zones west to east, each beside its standard offset; the
  one in force wears the current mark and the page opens on it; choosing
  one sets it and goes back.
- Paired browsers: each browser this console paired, by its name and the
  day it was last seen; choosing one forgets it (its key, its open
  sessions), and with two or more Remove all forgets every one. Under them
  the SSH host key's fingerprint, for checking a first SSH connection
  reached this console.
- Bluetooth keyboard: the keyboard input switch and the link's state, the
  keyboards found (choosing one uses it), Scan and Forget.
- Last crash: the kernel's record, the core dump's size with a button that
  clears it where one is in flash, and Back.
- USB drive: off, what it does and Turn on (and why it did not, where it
  did not); on, where the card is, how to give it back, and Turn off.

The console's services reach the handlers through `SettingsPages`, which
the hosting console makes; the Bluetooth and USB pages' state is
`SettingsLayer`'s, which their poll reads each frame (`bt_poll`,
`usb_poll`).
"""

import uitree as ui
import uitree_app
import wallclock as _wc
import ssh_service as _ssh
from crash_guard import clear_core_dump, core_dump, crash_lines, last_crash

NONE_PAIRED = "None. Scan the code on Web console to pair one."
NO_HOST_KEY = "Made at SSH's first start (set a password: passwd)"

s = ui.state(
    zones=ui.model(key="tz", tz="", place="", off=""),
    zone="",
    sel=ui.row_of("zones"),
    browsers=ui.model(key="kid", kid="", name="", seen=""),
    many=False,
    fp="",
    bt_on=False,
    bt_name="",
    bt_state="",
    bt_msg="",
    bt_scanning=False,
    keyboards=ui.model(key="id", id="", name="", value=""),
    bt_sel=ui.row_of("keyboards"),
    crash=ui.model(key="id", id="", text=""),
    dump=False,
    usb_on=False,
    usb_say="",
    usb_dev=False,
    usb_why="",
)


def _day(t):
    """`t` (Unix seconds, as wallclock takes them) as the day it fell on."""
    y, m, d = _wc.localtime(t)[:3]
    return "%d-%02d-%02d" % (y, m, d)


# -- Time zone ------------------------------------------------------------------

def tz_opened():
    s.zones = [{"tz": tz, "place": place, "off": _wc.utc_label(_wc.parse(tz)[1])}
               for place, tz in _wc.ZONES]
    s.zone = _wc.zone()
    s.sel = s.zone if any(tz == s.zone for _p, tz in _wc.ZONES) else ""


def use(row):
    uitree_app.env().toggles.set_time_zone(row.tz)
    s.zone = row.tz
    ui.pop()


ui.hook("tz_opened", tz_opened)
ui.action("use", "Use", use, takes="row")


def tz_page():
    with ui.page(""):
        with ui.group("Time zone"):
            with ui.rows("zones", cur="sel", current="zone"):
                ui.link("use", "{.off}", label="{.place}")


# -- Paired browsers ------------------------------------------------------------

def read_paired():
    """The paired browsers and the host key's fingerprint, as the page shows them."""
    ws = uitree_app.env()
    web = getattr(ws, "webhost", None)
    rows = []
    if web is not None:
        try:
            rows = [{"kid": kid, "name": name or "A browser", "seen": _day(seen)}
                    for kid, _created, seen, name in web.browsers()]
        except Exception as exc:  # noqa: BLE001 -- a list is not worth a crash
            print("SETTINGS paired browsers:", exc)
    s.browsers = rows
    s.many = len(rows) > 1
    s.fp = _ssh.fingerprint(ws) or ""


def _forget(kid):
    web = getattr(uitree_app.env(), "webhost", None)
    if web is not None:
        web.forget(kid)
    read_paired()


def forget(row):
    _forget(row.kid)


def forget_all():
    _forget("all")


ui.hook("paired_opened", read_paired)
ui.action("forget", "Remove", forget, takes="row")
ui.action("forget_all", "Remove all", forget_all, hint="Remove")


def paired_page():
    with ui.page(""):
        with ui.group("Paired browsers"):
            ui.label(NONE_PAIRED, shown="!browsers")
            with ui.rows("browsers"):
                ui.link("forget", "Seen {.seen}", label="{.name}")
            ui.button("forget_all", "danger", shown="many")
        with ui.group("SSH host key"):
            ui.label(NO_HOST_KEY, shown="!fp")
            ui.label("{fp}", wrap="char", shown="fp")


# -- Bluetooth keyboard ---------------------------------------------------------

_NETS = 24                    # the keyboards the page lists


def _sl():
    return uitree_app.env().settings_layer


def bt_poll(sl):
    """The keyboard service as the page shows it (`SettingsLayer._bt_refresh`),
    the keyboards written only where they moved."""
    enabled, state, name, _preferred, _error = sl._bt_refresh()
    s.bt_on = bool(enabled)
    s.bt_name = name or "No keyboard"
    s.bt_state = state[:1].upper() + state[1:]
    s.bt_msg = sl.bt_msg
    s.bt_scanning = state == "scanning"
    devs = sl.bt_devices
    if devs != sl.bt_shown:
        sl.bt_shown = devs
        rows = []
        for k in range(min(len(devs), _NETS)):
            _address, dev_name, rssi, preferred, connected = devs[k]
            rows.append({"id": "bt%d" % k, "name": str(dev_name),
                         "value": "Online" if connected else "Saved" if preferred
                         else "%d dBm" % int(rssi) if int(rssi) > -127 else ""})
        s.keyboards = rows


def bt_picked(row):
    _sl().bt_sel = int(row.id[2:])


def bt_use(row):
    sl = _sl()
    sl.bt_sel = int(row.id[2:])
    sl._bt_action("connect", sl.bt_devices[sl.bt_sel][0])


def bt_toggle():
    _sl()._bt_action("toggle")


def bt_scan():
    _sl()._bt_action("scan")


def bt_forget():
    _sl()._bt_action("forget")


ui.hook("bt_poll", bt_poll, takes="arg")
ui.hook("bt_picked", bt_picked, takes="row")
ui.action("bt_use", "Use", bt_use, takes="row")
ui.action("bt_toggle", "Keyboard input", bt_toggle)
ui.action("bt_scan", "Scan", bt_scan)
ui.action("bt_forget", "Forget the saved keyboard", bt_forget)


def bt_page():
    with ui.page(""):
        with ui.group("Bluetooth keyboard"):
            ui.toggle("Keyboard input", "bt_on", on="bt_toggle")
            ui.info("{bt_name}", "{bt_state}")
            ui.label("{bt_msg}", shown="bt_msg")
        with ui.group("Keyboards"):
            ui.label("{bt_scanning?Scanning...:No keyboards found.}", shown="!keyboards")
            with ui.rows("keyboards", cur="bt_sel", changed="bt_picked"):
                ui.link("bt_use", "{.value}", label="{.name}", icon="key")
        with ui.group("Options"):
            ui.link("bt_scan")
            ui.link("bt_forget")


# -- Last crash -----------------------------------------------------------------

def crash_opened():
    dump = core_dump()
    s.crash = [{"id": str(k), "text": line} for k, line in enumerate(crash_lines(last_crash(), dump))]
    s.dump = bool(dump)


def clear_dump():
    clear_core_dump()
    crash_opened()


def crash_back():
    ui.pop()


ui.hook("crash_opened", crash_opened)
ui.action("clear_dump", "Clear core dump", clear_dump)
ui.action("crash_back", "Back", crash_back)


def crash_page():
    with ui.page(""):
        with ui.group("Last crash"):
            with ui.rows("crash"):
                ui.label("{.text}", wrap="word")
            ui.button("clear_dump", shown="dump")
            ui.button("crash_back")


# -- USB drive ------------------------------------------------------------------

# Its words, by the drive's state (usb_drive.STOPPED .. EJECTED), and what it
# adds while on.
USB_SAYS = ("Show your memory card on a computer over the USB cable. "
            "Games and apps stay closed while it is on.",
            "Waiting for a computer. Plug the USB cable in.",
            "On the computer now, as a drive.",
            "The computer let the card go.")
USB_EJECT = "Eject it on the computer and it comes back here."
USB_SERIAL_OFF = "The serial port is off while it is on."
USB_SERIAL_BACK = "The serial port comes back when it is off."


def usb_poll(sl):
    d = sl._usb.drive()
    st = d.state()
    sl._usb_seen = st
    s.usb_on = bool(d.on)
    s.usb_say = USB_SAYS[st]
    s.usb_dev = bool(d.dev_channel)
    s.usb_why = d.why or ""


def turn_on():
    _sl()._usb.turn_on()


def turn_off():
    _sl()._usb.turn_off()


ui.hook("usb_poll", usb_poll, takes="arg")
ui.action("turn_on", "Turn on", turn_on)
ui.action("turn_off", "Turn off", turn_off)


def usb_page():
    with ui.page(""):
        with ui.group("USB drive"):
            ui.label("{usb_say}", wrap="word")
            ui.label(USB_EJECT, wrap="word", shown="usb_on")
            ui.label(USB_SERIAL_BACK, wrap="word", shown="usb_on && usb_dev")
            ui.label(USB_SERIAL_OFF, wrap="word", shown="!usb_on && usb_dev")
            ui.label("{usb_why}", wrap="word", shown="!usb_on && usb_why")
            ui.button("turn_off", "danger", shown="usb_on")
            ui.button("turn_on", shown="!usb_on")


class SettingsPages:
    """The pages as Settings hosts them, each on its sub page's host: opened
    on each visit (its hook), drawn into the sub page's frame, closed by its
    own `ui.pop()` through `close(name)`."""

    # name -> (its build, its opening hook, its frame's poll)
    PAGES = {"tz": (tz_page, "tz_opened", None), "paired": (paired_page, "paired_opened", None),
             "bt": (bt_page, None, bt_poll), "crash": (crash_page, "crash_opened", None),
             "usb": (usb_page, None, usb_poll)}

    def __init__(self, sl, host, damage, close):
        self.sl = sl
        self.pages = {}
        for name, (build, _hook, _poll) in self.PAGES.items():
            self.pages[name] = uitree_app.hosted_page(build, host, damage, close=self._closer(close, name),
                                                      env=sl.ws)

    @staticmethod
    def _closer(close, name):
        return lambda: close(name)

    def open(self, name):
        hook = self.PAGES[name][1]
        self.pages[name].open(hook=hook or "opened")

    def close(self, name):
        self.pages[name].close()

    def draw(self, name, cv, th, rect, desk, dt):
        page, poll = self.pages[name], self.PAGES[name][2]
        if poll is not None:
            page.run(poll, self.sl, action=poll.__name__)
            ui.commit(page)
        page.paint(dt, cv, th, rect, desk)
