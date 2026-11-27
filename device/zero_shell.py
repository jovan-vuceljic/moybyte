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
    /proc/console's name, board and firmware (neofetch's rows). The other
    role commands and the installed ones are not served on this board
    (ABSENT: "not served here", "not found"), the store's C commands
    (`settings`, `pkg list`) serving in their place; everything else is the
    console's (its processes, /proc's and /dev's rows), which this board has
    not got, so it answers as a console with its VM stopped does
    (NEEDS_VM).
  * THE CONSOLE ssh_service reads: the store's carts root, the board's name,
    its webhost (the browsers `passwd -l` lists) and no WiFi lease
    (`wifi_hold` None): the station and the mDNS name are the board's, up
    while it serves its webhost.
  * WIFI: the door answers `wifi` too, over the page's Wi-Fi panel's backend
    (zero_wifi.ZeroWifi, the webhost's `wifi`), one store of saved networks:
    `wifi [status]`, `scan` (asked, then stepped while the webhost's poll runs
    it) and `list`; `join` moves the board as the panel's does, its way back
    included, and asks first (-y says yes), since the session reaches the
    board over the network it leaves and ends with the move; `forget` refuses
    the network in use, which the next boot would not find (with no other
    saved, the board starts its setup).

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
RUNNING = -100                  # a role command goes on: the session steps it again
NOT_RUN, INTERRUPTED = 126, 130     # moy_proc_exit.h: asked a question; Ctrl-C
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
        self.jobs = {}          # a session's waiting role command: job -> generator

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
        if argv and argv[0] == "wifi":
            self.v_stop(job)
            self.jobs[job] = self._wifi(*argv[1:])
            return self.v_step(job)
        if argv and argv[0] == "service":
            return self.service(list(argv[1:]))
        if not argv or argv[0] != "passwd":
            return ABSENT
        import ssh_service
        try:
            return ssh_service.passwd(self, list(argv[1:]))
        except OSError as e:
            self.err("passwd", str(e))
            return 1

    def v_spawn(self, *argv):
        return ABSENT               # no installed commands

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

    # A role command is a generator (runtime/shell/sh_door.py's protocol):
    # `role JOB ...` starts it, each `step JOB` a turn of the poll loop later
    # runs it to its next `yield`, and `stop JOB` (Ctrl-C) closes it. A job
    # this door does not hold is the console's (NEEDS_VM).

    def v_step(self, job):
        gen = self.jobs.get(job)
        if gen is None:
            return NEEDS_VM
        try:
            next(gen)
            return RUNNING
        except StopIteration as e:
            r = e.value
        except Exception as e:  # noqa: BLE001 -- a role's failure is its exit
            self.err("wifi", str(e))
            r = 1
        del self.jobs[job]
        return r

    def v_stop(self, job):
        gen = self.jobs.pop(job, None)
        if gen is None:
            return NEEDS_VM
        gen.close()
        return INTERRUPTED

    def _wifi(self, verb="status", *a):
        w = getattr(self.ws.webhost, "wifi", None)
        yes = a[:1] == ("-y",)
        if yes:
            a = a[1:]
        n = {"status": 0, "scan": 0, "list": 0, "forget": 1, "join": 2}.get(verb)
        if n is None or len(a) > n or (n and not a) or (yes and n != 2):
            self.err("usage", "wifi [status] | scan | list | join [-y] SSID [PASSWORD]"
                     " | forget SSID")
            return 2
        if w is None:
            self.err("wifi", "this board has none")
            return 1
        up, on, ip, _ = w.link()        # `on` None while down
        if verb == "status":
            self.out("connected to %s (%s)\n" % (on, ip) if up else "not connected\n")
            return 0
        saved = []
        for net in w.saved():
            saved.append(net["ssid"])
        if verb == "list":
            for ssid in saved:
                self.out("%-6s  %s\n" % ("in use" if ssid == on else "", ssid))
            return 0
        if verb == "scan":
            # bounded by ZeroWifi's own SCAN_MS: the webhost's poll steps a
            # busy ZeroWifi every turn (moy_webhost.WebHost.poll), and a scan
            # that has not ended by then ends with what it found
            sid = w.scan_id
            w.request({"action": "scan"})
            while w.scan_id == sid:
                yield
            on = w.link()[1]
            for ssid, sig, locked in w.nets:
                self.out("%3d%%  %-6s  %-6s  %s\n" % (
                    sig, "locked" if locked else "open",
                    "in use" if ssid == on else "saved" if ssid in saved else "", ssid))
            return 0
        if a[0] == on:
            if verb == "forget":
                self.err("wifi", "%s is the network in use: join another first" % on)
                return 1
            self.out("already on %s\n" % on)
            return 0
        if verb == "forget":
            ok, msg = w.request({"action": "forget", "ssid": a[0]})
            if not ok:
                self.err("wifi", "%s: %s" % (a[0], msg))
            return 0 if ok else 1
        if up and not yes:
            # moy_sh.h's question: the answer typed to it in this line's
            # earlier run, else None once asked (the line runs again with the
            # answer); a session that asks nothing (a stream face) says how
            # to say yes
            try:
                said = self.io.answer()
                if said is None:
                    self.io.ask("Leave %s for %s? [y/N] " % (on, a[0]), False)
                    return NOT_RUN
            except (AttributeError, OSError):
                self.err("wifi", "it asks first: -y says yes")
                return 1
            if said.strip().lower() not in ("y", "yes"):
                return 1
        ok, msg = w.request({"action": "join", "ssid": a[0],
                             "password": a[1] if len(a) > 1 else None})
        if not ok:
            self.err("wifi", msg)
            return 1
        self.out("moving to %s: the board is %s.local there%s\n"
                 % (a[0], w.name, ", or back on %s if %s does not answer in %d s"
                    % (on, a[0], w.join_ms // 1000) if up else ""))
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

