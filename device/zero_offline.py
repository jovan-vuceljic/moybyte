"""The browser console's own copy on a Zero whose console is online
(board.toml's `[web] console`): "Works offline" in the page's Settings
(owner, 2026-11-26), off by default.

On, the board installs the add-on its image fits through the release's
signed index (zero_host.make_addon's step, web_addon.AddonStep), serves its
own pack, which the loader prefers to a mirror (`GET /sync`'s `local`), and
brings the matching one after an update; off, the step takes every add-on
folder back and the loader is online again. The choice is the store's
`system/console_offline`, so it outlives an update. `/official` carries it
(web_addon.OfficialCarts' `offline`); the page's row is
firmware/web_runner/offline_link.py. An image that stages no copy of this
module (the C3, with no updater to fetch the add-on by) offers none."""

import os

import zero_host as _zh

FILE = _zh.SYSTEM_DIR + "/console_offline"


def chosen():
    """Whether this board's owner asked for the console's own copy."""
    try:
        os.stat(FILE)
        return True
    except OSError:
        return False


def _mb(n):
    return "%.1f MB" % (n / 1e6)


class Offline:
    """`/official`'s "offline": the choice and where it stands, over
    make_addon's step `addon` and the store at `root`."""

    def __init__(self, addon, root):
        self.addon = addon
        self.root = root

    def _needs(self):
        try:
            import moy_web
            return int(moy_web.stamp().split()[1]) + _zh.ADDON_FILES
        except (ImportError, AttributeError, ValueError, IndexError):
            return None

    def state(self):
        """{"on", "installed", "needs", "free", "busy", "progress", "error"}:
        the choice, whether the board serves its own copy, the bytes the copy
        takes and the store has free, and its install while it runs."""
        try:
            import web_addon
            installed = web_addon.page_state() == web_addon.STATE_READY
        except ImportError:
            installed = False
        a = self.addon
        return {"on": chosen(), "installed": installed, "needs": self._needs(),
                "free": _zh._free_bytes(self.root), "busy": a.busy(),
                "progress": a.progress, "error": a.error}

    def choose(self, on):
        """The owner's choice: (ok, message)."""
        a = self.addon
        if on:
            need, free = self._needs(), _zh._free_bytes(self.root)
            if need is None:
                return False, "This image names no browser console."
            if free is not None and free - _zh.SEED_RESERVE < need:
                return False, "It needs %s and this board has %s free." % (
                    _mb(need), _mb(max(0, free - _zh.SEED_RESERVE)))
            with open(FILE, "w") as f:
                f.write("1\n")
            a.drop(keep=True)
            return True, "Installing the browser console on this board."
        try:
            os.remove(FILE)
        except OSError:
            pass
        a.drop(keep=False)
        return True, "The browser console is online again."
