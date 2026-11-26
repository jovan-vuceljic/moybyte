"""The Zero's on-board services (#256): an installed app's service runs on
this board while the app's window runs in the browser the board serves.

Moy Mesh is the case it is built for: its service holds the board's LoRa
radio and keeps listening with no browser open (a base station), and a page
that opens Moy Mesh talks to it over the live socket's apps' channel 'm'
(native/moy_net/moy_live_svc.c), whose page half (moy_svc_web.c) keeps the
page from starting a service of its own (runtime/system/scheduler.py's
`on_board`).

WHAT RUNS. A Lua app's own service (`"moybyte": {"entries": {"service":
"<file>.lua"}}`), as the console runs one (runtime/system/scheduler.py's
`as_service`, `wants_autostart`): its shared scripts (its `sources` before
its main) and then its entry, each a chunk, on moycore's service tier
(native/moycore/moycore_svc.h), on a task of its own; no cart runs here. At boot the services whose app asks for
`autostart` start. A service runs under the grant its manifest's
permissions make (native/moy_app: `prefs`, the device handles its `lora`
reaches); this board keeps no consent record of its own (a page's are LOCAL,
runtime/carts/moy_sync.py's SYSTEM_KEYS), so a cart it installed runs under
its manifest as written, as a console's does where it holds none.

THE BUDGET. The board gives its services the RAM board.toml's [services]
names (moycore.svc_budget(): every service's state summed, the allocator's
cap, moycore_svc.h's THE BUDGET). A start is admitted only where what is
left holds what the service needs (its manifest's `service_kib`, else
LUA_SVC_NEED, the console's figure for a start); else it is refused with
the reason, and the app's service runs in the page while a
page has it open, as it does on a board that runs none. A service that ends
(an error, the budget reached) is no longer served, and the page runs it
there from its next open.

THE ROWS. The app's prefs are the kernel's settings rows (moy_app.kernel),
read from the store's `system/settings` at the start and written back as a
service changes them (`turn`); the webhost's system root reads and writes
the same rows (device/moy_webhost.py's StoreSystem), so a page's batch and a
service's prefs have one writer.

THE CALLS. What a service asks the console (moycore_svc.h, CONSOLE CALLS)
waits on the VM's queue, which `turn` serves on the store host's loop: the
console's name, its clock, the app's own keys (runtime/system/app_keys.py);
any other call is refused.
"""

import json
import os
import time

import moy_evq as _E

try:
    import moy_log as _L
except ImportError:  # pragma: no cover - every image with services has it
    _L = None

ENTRY = "service"
LUA_SVC_NEED = 40 << 10         # runtime/system/sched_lua.py's: a service at its start
SVC_EXITED = 4                  # moycore_svc.h's MOYCORE_SVC_EXITED
INFO, ERR = 6, 3
CALLS_MAX = 16                  # console calls answered a turn


def runtime():
    """moycore's services where this image runs them, else None."""
    try:
        import moycore
    except ImportError:
        return None
    return moycore if hasattr(moycore, "svc_start") else None


def _log(level, pid, text):
    print("ZERO svc:", text)
    if _L is not None:
        _L.write(level, pid, text)


def _read(path):
    with open(path) as f:
        return f.read()


def entry_of(m):
    """The Lua service entry manifest `m`'s `moybyte` names, or None
    (scheduler.entry_of's rule, Lua alone)."""
    got = (m.get("moybyte") or {}).get("entries")
    f = got.get(ENTRY) if isinstance(got, dict) else None
    if not isinstance(f, str) or not f.endswith(".lua") or f[0] == "/" or ".." in f.split("/"):
        return None
    return f


def chunks(folder, m, entry):
    """The service's scripts in load order, as moycore.svc_start takes them:
    the shared ones (its `sources` before its main, the entry not among
    them), then the entry, named after the service (scheduler.as_service)."""
    out = []
    main = m.get("main")
    for n in m.get("sources") or ():
        if n == main:
            break
        if isinstance(n, str) and n != entry and n.endswith(".lua"):
            out.append((_read(folder + "/" + n), "@" + n))
    out.append((_read(folder + "/" + entry), None))
    return out


def need(m):
    """The bytes manifest `m`'s service needs to run: its `service_kib`
    (docs/app_api_v1.md section 7), else a service's start (LUA_SVC_NEED)."""
    kib = (m.get("moybyte") or {}).get("service_kib")
    if isinstance(kib, int) and not isinstance(kib, bool) and kib > 0:
        return kib << 10
    return LUA_SVC_NEED


class Service:
    """One app's service on this board."""

    def __init__(self, app_id, folder, perms):
        self.app_id = app_id
        self.folder = folder
        self.perms = perms
        self.pid = 0
        self.h = 0              # its moycore handle while it lives
        self.grant = None
        self.why = ""           # why it ended or was refused


class Services:
    """The services this board runs, over the kernel's settings rows and
    app ABI state, made at the host's start."""

    def __init__(self, carts_root):
        import moy_app
        import moy_docs
        import moy_spine
        self.root = carts_root
        self.svc = runtime()
        self.rows = moy_spine.kernel_settings(self._save, True)
        self.rows.adopt(moy_docs.load_system(carts_root))
        kernel = getattr(moy_app, "kernel", None)
        # The kernel's state on a board, its prefs the kernel's rows; a
        # host's own over the same rows (runtime/shell/console.py's _app_abi).
        self.app = kernel(True) if kernel is not None else moy_app.App(self.rows)
        self.running = {}       # app id -> Service

    def _save(self, text):
        import moy_carts
        try:
            moy_carts.save_system(text, self.root)
        except OSError as e:
            print("ZERO svc: the settings were not written:", e)
            return False
        return True

    # -- the carts --------------------------------------------------------------

    def installed(self):
        """(app id, folder, manifest) of each installed app declaring a Lua
        service."""
        import moy_app
        out = []
        try:
            names = os.listdir(self.root)
        except OSError:
            return out
        for name in names:
            folder = self.root + "/" + name
            try:
                m = json.loads(_read(folder + "/manifest.json"))
            except (OSError, ValueError):
                continue
            if isinstance(m, dict) and m.get("runtime") == "lua" and entry_of(m):
                out.append((moy_app.id_for(m.get("id"), m.get("title")), folder, m))
        return out

    def boot(self):
        """The services whose app asks for `autostart` started (the
        console's rule, scheduler.wants_autostart). Answers the app ids
        started."""
        out = []
        for app_id, folder, m in self.installed():
            perms = (m.get("moybyte") or {}).get("permissions") or ()
            if "autostart" in perms and self.start(app_id, folder, m) is not None:
                out.append(app_id)
        return out

    # -- a service's life ----------------------------------------------------------

    def room(self, need):
        """Why a service needing `need` bytes does not fit the board's
        budget, or None."""
        budget, held = self.svc.svc_budget()
        if budget is not None and budget - held < need:
            return ("it needs %d KB and this board gives its services %d KB, %d KB of it free"
                    % (need >> 10, budget >> 10, (budget - held) >> 10))
        return None

    def start(self, app_id, folder, m):
        """App `app_id`'s service started from `folder` (manifest `m`) and
        served to the page's windows: its pid, or None with the reason
        logged, the app then running its service in the page."""
        import moy_app
        if app_id in self.running:
            return self.running[app_id].pid
        perms = tuple((m.get("moybyte") or {}).get("permissions") or ())
        s = Service(app_id, folder, perms)
        pid = _L.spawn(app_id) if _L is not None else 1
        s.pid = pid
        why = (self.room(need(m)) if self.svc is not None
               else "this image runs no Lua services")
        if why is None:
            try:
                src = chunks(folder, m, entry_of(m))
            except OSError as e:
                why = "its scripts do not read: %s" % e
        if why is not None:
            s.why = why
            _log(ERR, pid, "%s: %s" % (app_id, why))
            return None
        roles, kind = moy_app.policy(perms)
        try:
            s.grant = self.app.grant(app_id, roles, kind=kind, ns=app_id, run=True,
                                     owner=pid)
            self.app.grant_devs(s.grant, perms, folder)
            recv = (m.get("moybyte") or {}).get("receives")
            recv = "\n".join(r for r in recv if isinstance(r, str)) if isinstance(recv, list) else ""
            _E.open(pid, app_id, recv, False, "alarms" in perms, "notifications" in perms)
            s.h = self.svc.svc_start(pid, app_id, src, None, self.app.run(s.grant, roles))
        except (OSError, ValueError) as e:
            s.why = "its start: %s" % e
            _log(ERR, pid, "%s: %s" % (app_id, s.why))
            self._end(s)
            return None
        self.running[app_id] = s
        self._serve(app_id, True)
        _log(INFO, pid, "%s: started on this board" % app_id)
        return pid

    def stop(self, app_id):
        """App `app_id`'s service told to stop (its `moy_stop`); its end is
        the next turns'."""
        s = self.running.get(app_id)
        if s is not None and s.h:
            self.svc.svc_stop(s.h)

    def _serve(self, app_id, on):
        import moy_net
        fn = getattr(moy_net, "live_serve", None)
        if fn is not None:
            fn(app_id, on)

    def _end(self, s):
        if s.grant is not None:
            self.app.end(s.grant)
            s.grant = None
        try:
            _E.close(s.pid)
        except OSError:
            pass

    def info(self):
        """[(app id, pid, state, heap, why)] of the services, for `mem`."""
        out = []
        for app_id, s in self.running.items():
            got = self.svc.svc_info(s.h) if s.h else None
            out.append((app_id, s.pid, got[0] if got else SVC_EXITED, got[2] if got else 0,
                        got[5] if got else s.why))
        return out

    # -- the loop ----------------------------------------------------------------------

    def turn(self):
        """The store host's turn: the VM's queue served (the hops the
        services' rows ask for, their console calls answered), a prefs
        write a service made saved, and an ended service reaped, its app no
        longer served."""
        if not self.svc.svc_tasks():
            self.svc.svc_step()             # a host's: no task of their own
        self._answer()
        if self.rows.dirty():
            self.rows.flush()
        for app_id in list(self.running):
            s = self.running[app_id]
            got = self.svc.svc_info(s.h)
            if got is not None and got[0] != SVC_EXITED:
                continue
            if got is not None:
                s.why = got[5] or "exited %d" % got[1]
                self.svc.svc_reap(s.h)
            s.h = 0
            del self.running[app_id]
            self._serve(app_id, False)
            self._end(s)
            _log(INFO if not got or not got[1] else ERR, s.pid,
                 "%s: ended on this board: %s" % (app_id, s.why))

    def _answer(self):
        for _ in range(CALLS_MAX):
            if not _E.serve():
                return
            req = _E.next_call()
            if req is None:
                return
            ticket, pid, name, args = req
            ans = None
            try:
                ans = json.dumps(self.call(pid, name, json.loads(args)))
            except Exception as exc:  # noqa: BLE001 -- refused, the service told
                _log(ERR, pid, "%s: %s: %s" % (name, type(exc).__name__, exc))
            _E.answer(ticket, ans)

    def _app_of(self, pid):
        for app_id, s in self.running.items():
            if s.pid == pid:
                return app_id
        return None

    def call(self, pid, name, args):
        """Console call `name` of process `pid` with `args`, answered as the
        console answers it (runtime/system/moybyte.py); ValueError for one
        this board does not serve."""
        if name == "moybyte.clock":
            return time.time() if not (args and args[0]) else None
        if name == "moybyte.name":
            from zero_host import identity, HOSTNAME
            return identity().get("name") or HOSTNAME
        app = self._app_of(pid)
        if app is not None and name in ("moybyte.key_make", "moybyte.key_public",
                                        "moybyte.key_shared"):
            import app_keys
            if name == "moybyte.key_make":
                return app_keys.make(self.root, app, args[0])
            if name == "moybyte.key_public":
                return app_keys.public(self.root, app, args[0])
            return app_keys.shared(self.root, app, args[0], args[1])
        raise ValueError("not served on this board")


def make(carts_root):
    """The board's services, or None where this image runs none."""
    if runtime() is None:
        return None
    try:
        return Services(carts_root)
    except Exception as exc:             # noqa: BLE001 -- the store serves regardless
        print("ZERO svc: unavailable:", exc)
        return None
