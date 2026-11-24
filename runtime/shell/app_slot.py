"""A declared system app until it first runs (`AppSlot`): what the
console registers from each of `app_decls.APPS` at boot, which
`console_spine.Spine.built` replaces with the app at its first ask."""

from moy_store_base import builtin_name as _builtin_name


class AppSlot:
    """A declared system app (`app_decls.APPS`) until it first runs: what
    the shell asks of an app it has not built -- its id, its title and the
    identity cart it claims -- with no import of its module. `Spine.built`
    makes the app at its first ask (an open, its layer looked up) and puts
    it where the slot stood; the built app claims what its declaration
    claims (`is_app`)."""

    def __init__(self, decl, ctx=None, service=None):
        self.id = decl["id"]
        self.TITLE = decl.get("name") or decl["title"]
        self.decl = decl
        self.ctx = ctx                  # its context, where a service needed it at boot
        self.service = service
        self.app = None                 # the app, once built

    def is_app(self, cart):
        """The shipped identity cart: its title, its marker permission, its
        folder (a path-less embedded cart, its version); never a renamed or
        copied cart."""
        d = self.decl
        if not cart or cart.get("title") != d["title"]:
            return False
        marker = d.get("marker")
        if marker is not None and marker not in (cart.get("permissions") or ()):
            return False
        path = cart.get("path")
        if not path:                    # embedded fallback cart (no writable store)
            return marker is None or int(cart.get("version", 0)) >= 1
        return _builtin_name(path) == d["folder"] + ".moy"
