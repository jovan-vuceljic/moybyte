"""A Zero's Wi-Fi, managed from the page it serves: the backend of the
webhost's sealed `/wifi` (`moy_webhost.WebHost.wifi`), over this board's
saved networks (`/moy/wifi.json`, `{"networks": [{"ssid", "password"}]}`,
the document a console's Wi-Fi panel writes) and the kernel's driver
(`moy_net.wifi_*`).

    GET  /wifi   the document (`answer`): the network the board is on, its
                 address and signal, the saved networks BY NAME (a password
                 never leaves the board), the last scan's networks, a
                 switch under way and the last switch's verdict
    POST /wifi   `{"action": ...}`, answered at once with the document; the
                 work is the poll's (`step`):
                   scan                   a scan, polled until it ends
                   add     ssid password  saved, without leaving this network
                   forget  ssid           unsaved, without leaving it either
                   join    ssid [password]  the board moves to `ssid`

THE SWITCH. The page reaches this board over the network it is about to
leave, so a join is a switch with a way back: the answer leaves first
(LEAVE_MS), the board asks for the new network and gives it JOIN_MS; a link
up there saves it first in the list (the next boot walks the list in order),
and anything else takes the board back to the network it left, for up to
BACK_MS, without saving a thing. The verdict is `last` in the document,
keyed by the switch's `id`, which a page that found the board again reads.
A board that reaches neither calls `stranded` (zero_host walks every saved
network, and resets into setup with none).

`radio` is anything with moy_net's wifi functions (the twin's fake,
firmware/web_runner/serve.py). Nothing here waits: the scan and the join
are asked and polled, one slice per poll of the board's loop.
"""

import json

from ticks import _ticks_ms as ticks_ms, _ticks_diff as ticks_diff

JOIN_MS = 15000         # the new network's window
BACK_MS = 15000         # the old network's, after a join that failed
LEAVE_MS = 500          # the POST's answer is on the wire before the radio moves
SCAN_MS = 12000         # a scan that has not ended by then has failed
# The disconnect reasons that end a join at once (a wrong password), as
# device_wifi.REFUSED; tests/test_zero_wifi.py holds the two equal.
REFUSED = (15, 202, 204)
SSID_MAX = 32
PASSWORD_MAX = 63


def _sig(rssi):
    return max(0, min(100, 2 * (int(rssi) + 100)))    # -100 -> 0%, -50 -> 100%


class ZeroWifi:
    """The `/wifi` backend: `answer()` the document, `request(doc)` a POST,
    `step()` the poll's slice while `busy()`."""

    def __init__(self, store, name, radio=None, stranded=None,
                 join_ms=JOIN_MS, back_ms=BACK_MS, leave_ms=LEAVE_MS):
        if radio is None:
            import moy_net as radio
        self.store = store
        self.name = name
        self.radio = radio
        self.stranded = stranded
        self.join_ms = join_ms
        self.back_ms = back_ms
        self.leave_ms = leave_ms
        self.nets = []          # [[ssid, signal %, locked]], the last scan's
        self.scan_id = 0        # scans ended since boot
        self._scan_at = None    # when the running scan was asked, else None
        self._sw = None         # the switch under way: [id, ssid, password, prev, phase, at, why]
        self._ids = 0
        self.last = None        # the last switch's verdict

    # -- the saved networks -------------------------------------------------

    def saved(self):
        """The saved networks, as wifi.json lists them."""
        try:
            with open(self.store) as f:
                doc = json.load(f)
        except (OSError, ValueError):
            return []
        nets = doc.get("networks") if isinstance(doc, dict) else doc
        return [n for n in (nets or []) if isinstance(n, dict) and n.get("ssid")]

    def _write(self, nets):
        with open(self.store, "w") as f:
            f.write(json.dumps({"networks": nets}))

    def _password(self, ssid):
        for n in self.saved():
            if n["ssid"] == ssid:
                return n.get("password") or n.get("key") or ""
        return None

    def _save(self, ssid, password, first):
        nets = self.saved()
        at = None
        for i, n in enumerate(nets):
            if n["ssid"] == ssid:
                at = i
        if first or at is None:
            nets = [n for n in nets if n["ssid"] != ssid]
            row = {"ssid": ssid, "password": password}
            if first:
                nets.insert(0, row)
            else:
                nets.append(row)
        else:
            nets[at] = {"ssid": ssid, "password": password}
        self._write(nets)

    # -- the document -------------------------------------------------------

    def _link(self):
        st = self.radio.wifi_status()
        up = bool(st[2] and st[4])
        return up, (st[3] if up else None), (st[4] if up else None), st[5]

    def answer(self, ok=None, msg=None):
        """The `/wifi` document, as JSON text."""
        up, ssid, ip, _ = self._link()
        signal = None
        for n in self.nets:
            if n[0] == ssid:
                signal = n[1]
        sw = self._sw
        doc = {"v": 1, "name": self.name, "host": self.name + ".local",
               "connected": up, "ssid": ssid, "ip": ip, "signal": signal,
               "saved": [n["ssid"] for n in self.saved()],
               "scanning": self._scan_at is not None, "scan_id": self.scan_id,
               "nets": self.nets,
               "switch": None if sw is None else {"id": sw[0], "ssid": sw[1], "phase": sw[4]},
               "last": self.last, "join_ms": self.join_ms, "back_ms": self.back_ms}
        if ok is not None:
            doc["ok"] = ok
            doc["message"] = msg or ""
        return json.dumps(doc)

    # -- the requests -------------------------------------------------------

    def request(self, doc):
        """A POST's `{"action", ...}`: (ok, message). Only asks; `step` works."""
        action = doc.get("action") or ""
        ssid = doc.get("ssid")
        password = doc.get("password")
        if action == "scan":
            if self._scan_at is None:
                self._scan_at = ticks_ms()
                self._scan_poll()
            return True, "scanning"
        if action not in ("add", "forget", "join"):
            return False, "unknown action %r" % action
        if not isinstance(ssid, str) or not ssid or len(ssid.encode()) > SSID_MAX:
            return False, "no network named"
        if password is not None and (not isinstance(password, str)
                                     or len(password.encode()) > PASSWORD_MAX):
            return False, "that password is too long"
        if action == "add":
            self._save(ssid, password or "", False)
            return True, "saved"
        if action == "forget":
            if self._password(ssid) is None:
                return False, "not saved"
            self._write([n for n in self.saved() if n["ssid"] != ssid])
            forget = getattr(self.radio, "wifi_forget", None)
            if forget is not None:
                forget(ssid)
            return True, "forgotten"
        if self._sw is not None:
            return False, "a switch is under way"
        up, now, _, _ = self._link()
        if password is None:
            password = self._password(ssid)
        if up and now == ssid:
            if password is not None and doc.get("password") is not None:
                self._save(ssid, password, True)
            return True, "already"
        prev = None
        if up:
            prev = (now, self._password(now) or "")
        self._ids += 1
        self._sw = [self._ids, ssid, password or "", prev, "leave", ticks_ms(), ""]
        return True, "switching"

    def busy(self):
        return self._scan_at is not None or self._sw is not None

    # -- the poll's slice ---------------------------------------------------

    def step(self):
        """One slice of the scan or the switch; True when it moved."""
        did = False
        if self._scan_at is not None:
            did = self._scan_poll()
        if self._sw is not None:
            did = self._switch() or did
        return did

    def _scan_poll(self):
        try:
            got = self.radio.wifi_scan(False)
        except OSError:
            got = []
        if got is None:
            if ticks_diff(ticks_ms(), self._scan_at) < SCAN_MS:
                return False
            got = []
        best = {}
        for ssid, rssi, auth in got:
            if isinstance(ssid, bytes):
                try:
                    ssid = ssid.decode()
                except UnicodeError:
                    continue
            if ssid and (ssid not in best or rssi > best[ssid][0]):
                best[ssid] = (rssi, auth != 0)
        self.nets = sorted(([s, _sig(r), lk] for s, (r, lk) in best.items()),
                           key=lambda n: -n[1])
        self.scan_id += 1
        self._scan_at = None
        return True

    def _switch(self):
        sw = self._sw
        waited = ticks_diff(ticks_ms(), sw[5])
        if sw[4] == "leave":
            if waited < self.leave_ms:
                return False
            print("ZERO wifi: switching to", sw[1])
            self._phase("join")
            try:
                self.radio.wifi_connect(sw[1], sw[2])
            except (OSError, ValueError):
                sw[6] = "the radio refused that network"
                return self._back()
            return True
        up, ssid, ip, reason = self._link()
        if sw[4] == "join":
            if up and ssid == sw[1]:
                self._save(sw[1], sw[2], True)
                self._mdns()
                print("ZERO wifi: switched to", sw[1], ip)
                return self._settle(True, sw[1])
            if reason in REFUSED:
                sw[6] = "the password was refused"
            elif waited >= self.join_ms:
                sw[6] = "no answer"
            else:
                return False
            print("ZERO wifi: %s on %s -- going back" % (sw[6], sw[1]))
            return self._back()
        if up:                              # back
            self._mdns()
            print("ZERO wifi: back on", ssid, ip)
            return self._settle(False, ssid)
        if waited < self.back_ms:
            return False
        print("ZERO wifi: the old network did not answer either")
        self._settle(False, None)
        if self.stranded is not None:
            self.stranded()
        return True

    def _phase(self, phase):
        self._sw[4] = phase
        self._sw[5] = ticks_ms()

    def _back(self):
        prev = self._sw[3]
        if prev is None:
            self.radio.wifi_disconnect()
            self._settle(False, None)
            if self.stranded is not None:
                self.stranded()
            return True
        self._phase("back")
        try:
            self.radio.wifi_connect(prev[0], prev[1])
        except (OSError, ValueError):
            pass
        return True

    def _settle(self, ok, on):
        sw, self._sw = self._sw, None
        self.last = {"id": sw[0], "ssid": sw[1], "ok": ok, "on": on, "why": sw[6]}
        return True

    def _mdns(self):
        try:
            self.radio.wifi_mdns(self.name)
        except OSError:
            pass
