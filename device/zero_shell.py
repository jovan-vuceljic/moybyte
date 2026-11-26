"""The Zero's terminal: the C shell over SSH, and SFTP into its store
(docs/os_2026-11/system.md sections 3 and 4).

The shell, its face and the server are the consoles' C (native/moy_sh,
native/moy_tty, native/moy_ssh); what is this board's own is the little a
console's Python gives them:

  * THE CONSOLE'S TASK. A face hops what must run on the VM's task (the
    store's files, the door into Python) to the console's frame tail. This
    board has no frame: its poll loop calls `tail()` each turn
    (zero_host.serve), and between turns a hop waits.
  * THE DOOR (native/moy_sh/moy_sh_board.h, the ROLE door's row
    MOY_SH_DOOR): `passwd`, `df`, `mem`, `ps` and, where the board runs
    apps' services (zero_svc), `service` answered here, and
    /proc/console's name, board and firmware (neofetch's rows); everything
    else is the console's (its processes, /proc's and /dev's rows, the
    installed and the other role commands), which this board has not got, so
    it answers as a console with its VM stopped does (NEEDS_VM), and the
    store's C commands (`settings`, `pkg list`) still serve.
  * THE CONSOLE ssh_service reads: the store's carts root, the board's name,
    its webhost (the browsers `passwd -l` lists) and no WiFi lease
    (`wifi_hold` None): the station and the mDNS name are the board's, up
    while it serves its webhost.

The password is the board's one (system/password): the one a browser pairs
with, set by the setup form or `provision.sh --password`, and changed with
`passwd` over SSH. With none set there is no SSH.

  start(carts_root, name, webhost)  the door bound and the server started
                                    where a password is set; the console, or None
  tail()                            a face's hop served on this task
"""

import gc
import os

try:
    import moy_loop
    import moy_tty
except ImportError:  # an image without the kernel or the face
    moy_loop = moy_tty = None

SH_DOOR = 0x7368                # native/moy_sh/moy_sh_board.h's MOY_SH_DOOR
ABSENT = -8
NEEDS_VM = -9                   # MOY_SH_DOOR_NEEDS_VM: the console's to answer
SHELL = 1


class Console:
    """What ssh_service reads of a console."""

    wifi = None
    wifi_hold = None
    wifi_release = None

    def __init__(self, carts_root, name, webhost=None):
        self.carts_root = carts_root
        self.system = {"name": name}
        self.webhost = webhost


def _io():
    try:
        import moy_sh
        return moy_sh
    except ImportError:
        return None


class Door:
    """`door(grant, row, args)`: the shell's crossings, `verb NUL arg ...`."""

    def __init__(self, ws, io=None):
        self.ws = ws
        self.io = io if io is not None else _io()

    def __call__(self, grant, row, args):
        if row != SH_DOOR:
            return ABSENT
        fields = bytes(args).split(b"\0")
        fn = getattr(self, "v_" + fields[0].decode(), None)
        if fn is None:
            return NEEDS_VM
        return fn(*[f.decode("utf-8", "replace") for f in fields[1:]])

    def out(self, text):
        if self.io is not None and text:
            self.io.write(1, text.encode())

    def err(self, name, text):
        if self.io is not None:
            self.io.write(2, ("%s: %s\n" % (name, text)).encode())

    def v_role(self, job, *argv):
        if argv and argv[0] == "service":
            return self.service(list(argv[1:]))
        if not argv or argv[0] != "passwd":
            return NEEDS_VM
        import ssh_service
        try:
            return ssh_service.passwd(self, list(argv[1:]))
        except OSError as e:
            self.err("passwd", str(e))
            return 1

    def service(self, a):
        """`service [status] | start|stop|restart APP | policy [APP [POLICY]]`
        over the board's apps' services (zero_svc), as the console's
        (runtime/shell/sh_roles.py's r_service) words them."""
        import zero_host
        svc = zero_host.SERVICES[0]
        if svc is None:
            return NEEDS_VM
        if not a or a[0] == "status":
            for app_id, pid, state, heap, why in svc.info():
                self.out("%d %s %s %d %s\n" % (pid, app_id, "exited" if state == 4 else "running",
                                                heap, svc.policy(app_id)))
            return 0
        if a[0] == "policy" and len(a) <= 3:
            if len(a) == 3:
                try:
                    svc.set_policy(a[1], a[2])
                except ValueError as e:
                    self.err("service", str(e))
                    return 2
                return 0
            names = [a[1]] if len(a) == 2 else [n for n, _f, _m in svc.installed()]
            for n in names:
                self.out("%s %s\n" % (n, svc.policy(n)))
            return 0
        if a[0] not in ("start", "stop", "restart") or len(a) != 2:
            self.err("service", "usage: service [status] | start|stop|restart APP"
                                " | policy [APP [never|on-crash|always]]")
            return 2
        if a[0] in ("stop", "restart"):
            svc.stop(a[1])
        if a[0] == "start" and svc.start_by_hand(a[1]) is None:
            self.err("service", "%s did not start: its log says why" % a[1])
            return 1
        if a[0] == "restart":
            svc.restart_by_hand(a[1])
        return 0

    def v_read(self, path):
        # /proc/console: what neofetch shows beside the shell's own rows,
        # where this board can answer it (runtime/shell/sh_door.py's
        # console_text on a console)
        if path != "/proc/console":
            return NEEDS_VM
        import moy_ota
        import ssh_service
        rows = (("name", ssh_service.hostname(self.ws)),
                ("board", moy_ota.BOARD_NAMES.get(moy_ota.BOARD, moy_ota.BOARD)),
                ("firmware", moy_ota.FIRMWARE_LABEL or moy_ota.FIRMWARE_NAME))
        return "".join("%s: %s\n" % (k, v) for k, v in rows if v).encode()

    def v_ps(self):
        used = gc.mem_alloc() if hasattr(gc, "mem_alloc") else 0
        out = "%d 0 shell running %d - zero_host\n" % (SHELL, used)
        import zero_host
        svc = zero_host.SERVICES[0]
        for app_id, pid, state, heap, _why in (svc.info() if svc is not None else ()):
            out += "%d %d %s %s %d - service\n" % (
                pid, SHELL, app_id, "exited" if state == 4 else "background", heap)
        return out

    def v_df(self, path):
        # A path no volume holds (/sd: this board has no card slot) is
        # absent, not the root's figures; a full littlefs reports free
        # blocks below zero, which is none.
        try:
            if path != "/":
                os.stat(path)
            st = os.statvfs(path)
        except (OSError, AttributeError):
            return ABSENT
        return "%d %d" % (st[1] * st[2], st[1] * max(0, st[3]))

    def v_mem(self):
        free = gc.mem_free() if hasattr(gc, "mem_free") else 0
        used = gc.mem_alloc() if hasattr(gc, "mem_alloc") else 0
        return "%d %d" % (free + used, free) if free + used else ABSENT

    def v_rescan(self, *names):
        # no shelf: the webhost reads the carts folder at every request
        return 0


def start(carts_root, name, webhost=None):
    if moy_loop is None or moy_tty is None:
        return None
    try:
        import ssh_service
    except ImportError:
        return None
    ws = Console(carts_root, name, webhost)
    try:
        moy_loop.role(Door(ws))
    except OSError as exc:
        print("ZERO ssh: no door:", exc)
        return None
    ssh_service.boot(ws)
    if webhost is not None:
        webhost.on_password = lambda: _claimed(ws)
    tail()      # the face's hops are this task's from the server's first connection
    st = ssh_service.status()
    print("ZERO ssh: %s" % ("off (no SSH server in this image)" if st is None
                             else "serving as %s.local" % ssh_service.hostname(ws)
                             if st[0] else "off (no password: passwd)"))
    return ws


def _claimed(ws):
    """A browser's claim set the password (moy_webauth.c, THE CLAIM): the
    server serves from now, as at a boot that finds one."""
    import ssh_service
    if ssh_service.start(ws):
        print("ZERO ssh: serving as %s.local" % ssh_service.hostname(ws))


def tail():
    if moy_tty is not None:
        moy_tty.tail()

