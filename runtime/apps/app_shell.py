# The Desk Lab apps' shared app-layer mixin (#78 family: Files).
# `ListShellApp` carries:
#
#   the persist tail          -- `_persist`, the CAN'T SAVE HERE / CAN'T SAVE
#                                <why> status contract over a role write's
#                                `(value, err)` pair;
#   the rename entry cap      -- RENAME_MAX.
#
# The host class binds `self._store` to its storage role (see
# runtime/shell/app_context.py) and draws its own views.
#
# MicroPython-safe; staged to both boards like every runtime/ module.

from layers import AppLayer
from app_context import NO_STORE


class ListShellApp(AppLayer):
    """Mixin for the app layers. `_persist` expects the host class to provide
    `status` and `_save_failed`."""

    def _persist(self, res):
        """Apply the shared status contract to a role write's `(value, err)`:
        no store -> CAN'T SAVE HERE; a failure -> CAN'T SAVE <why>; sets
        _save_failed both ways and returns True on success."""
        _value, err = res
        if err is None:
            self._save_failed = False
            return True
        self._save_failed = True
        self.status = ("CAN'T SAVE HERE" if err is NO_STORE
                       else ("CAN'T SAVE " + str(err))[:28])
        return False

    # Rename entry cap -- a label, not a paragraph.
    RENAME_MAX = 24
