# Map (grep -n a name to jump there):
#   rpc_result         an RPC result's data: the command and its strings
#   parse_rpc          an RPC frame's data -> (command, its fields)
#   urls               the addresses a joined board answers with
#   Improv             the commands, answered over the console
"""Improv Wi-Fi's commands, answered by a Zero over the cable that flashed it
(docs/web_console_online_2026-11.md §7; improv-wifi.com/serial).

The kernel takes the frames off the USB-Serial/JTAG console before the REPL
sees them (native/moy_kernel/moy_improv.h, the module `moy_improv`); this
module answers them, as `zero_setup` answers the access point's form: the
network a board joins, its name and the files they live in are the store
host's.

    0x01  the network: joined, saved first in wifi.json, then the address
    0x02  the current state, and the address once joined
    0x03  the device: "Moybyte", the firmware's label, the chip, the name
    0x04  the networks the station sees, one result each, then an empty one
    0x05  the hostname, which on a Zero is its name (an mDNS label)
    0x06  the name, cleaned into a label (zero_setup.clean_name)
    0x07  the network state: the flags, and the addresses while online

THE ADDRESS a joined board answers is its URL twice, by IP first (what every
browser opens) and by its `.local` name second, each carrying after its `#`
the board's id (the sign-in's, 32 hex digits) and, while the board has no
password, this boot's claim (moy_webauth.c, THE CLAIM): `#id=<id>&claim=<c>`.
The fragment never crosses the network. A browser that opens the URL sets
the board's first password with the claim and pairs with it at once.

A join from the setup access point is the store host's to finish: the board
leaves the access point and starts serving, and only then answers (`finish`),
so the URL it sends is one a browser can open.
"""

import json

READY, PROVISIONING, PROVISIONED = 0x02, 0x03, 0x04
NO_ERROR, INVALID, UNKNOWN_RPC, UNABLE, BAD_HOSTNAME = 0x00, 0x01, 0x02, 0x03, 0x05
STATE, ERROR, RPC, RESULT, BAD = 0x01, 0x02, 0x03, 0x04, -1
WIFI, CURRENT, INFO, SCAN, HOSTNAME, NAME, NETWORK = 1, 2, 3, 4, 5, 6, 7
SCAN_MAX = 16
FRAMES_A_POLL = 4


def rpc_result(cmd, strings):
    """An RPC result's data: the command, the strings' length, and each as
    its length and its UTF-8 bytes (a string cut to fit the frame)."""
    body = b""
    for s in strings:
        b = s if isinstance(s, bytes) else str(s).encode()
        room = 252 - len(body)
        if room < 0:
            break
        b = b[:room]
        body += bytes([len(b)]) + b
    return bytes([cmd, len(body)]) + body


def parse_rpc(data):
    """An RPC frame's data -> (command, [its length-prefixed fields]), or None
    when its lengths do not add up. A command with no data has no fields."""
    if len(data) < 2 or data[1] != len(data) - 2:
        return None
    body, fields, at = data[2:], [], 0
    while at < len(body):
        n = body[at]
        if at + 1 + n > len(body):
            return None
        fields.append(bytes(body[at + 1:at + 1 + n]))
        at += 1 + n
    return data[0], fields


def urls(ip, name, board_id, claim):
    """The URLs a joined board answers with: by IP, then by its .local name."""
    tail = "#id=" + board_id if board_id else ""
    if claim:
        tail += ("&" if tail else "#") + "claim=" + claim
    out = ["http://%s/%s" % (ip, tail)]
    if name:
        out.append("http://%s.local/%s" % (name, tail))
    return out


class Improv:
    """The commands over `port` (take() -> (type, data) or None, send(type,
    data)), answered from `board`, the store host's side:

        board.info()             -> (firmware label, chip)
        board.name()             -> the name (an mDNS label)
        board.rename(name)       -> the name it took, or None
        board.scan()             -> [(ssid bytes, rssi, locked)]
        board.join(ssid, pw)     -> the IP joined, or None
        board.save(ssid, pw)     the network, first in wifi.json
        board.ip()               -> the IP while serving, else None
        board.address()          -> (board id, claim) while serving

    `serving` is False while the setup access point is up; a join then leaves
    `joined` set for the loop that hosts the AP, and `finish()` answers it
    once the board serves."""

    def __init__(self, port, board, serving=True):
        self.port = port
        self.board = board
        self.serving = serving
        self.joined = None           # (ip, cmd) of a join answered by finish()

    def send_state(self, st):
        self.port.send(STATE, bytes([st]))

    def send_error(self, err):
        self.port.send(ERROR, bytes([err]))

    def result(self, cmd, strings):
        self.port.send(RESULT, rpc_result(cmd, strings))

    def addresses(self):
        ip = self.board.ip() if self.serving else None
        if not ip:
            return []
        board_id, claim = self.board.address()
        return urls(ip, self.board.name(), board_id, claim)

    def poll(self):
        """Answer the frames that are waiting: how many."""
        n = 0
        while n < FRAMES_A_POLL:
            f = self.port.take()
            if f is None:
                break
            n += 1
            kind, data = f
            if kind == BAD:
                self.send_error(INVALID)
            elif kind == RPC:
                try:
                    self.rpc(bytes(data))
                except Exception as exc:     # noqa: BLE001 -- the client hears why
                    print("ZERO improv:", type(exc).__name__, exc)
                    self.send_error(0xFF)
        return n

    def rpc(self, data):
        got = parse_rpc(data)
        if got is None:
            self.send_error(INVALID)
            return
        cmd, fields = got
        self.send_error(NO_ERROR)
        if cmd == WIFI:
            self.wifi(cmd, fields)
        elif cmd == CURRENT:
            urls_ = self.addresses()
            self.send_state(PROVISIONED if urls_ else READY)
            if urls_:
                self.result(cmd, urls_)
        elif cmd == INFO:
            label, chip = self.board.info()
            self.result(cmd, ["Moybyte", label, chip, self.board.name()])
        elif cmd == SCAN:
            self.scan(cmd)
        elif cmd in (HOSTNAME, NAME):
            self.name(cmd, fields)
        elif cmd == NETWORK:
            urls_ = self.addresses()
            self.result(cmd, [str(0x02 | (0x01 if urls_ else 0))] + urls_)
        else:
            self.send_error(UNKNOWN_RPC)

    def wifi(self, cmd, fields):
        if len(fields) != 2 or not fields[0] or len(fields[0]) > 32:
            self.send_error(INVALID)
            return
        ssid, pw = fields[0].decode(), fields[1].decode()
        self.send_state(PROVISIONING)
        ip = self.board.join(ssid, pw)
        if not ip:
            self.send_error(UNABLE)
            self.send_state(PROVISIONED if self.addresses() else READY)
            return
        self.board.save(ssid, pw)
        self.joined = (ip, cmd)
        if self.serving:
            self.finish()

    def finish(self):
        """The answer to a join, once the board serves: provisioned, and the
        URLs to open."""
        if self.joined is None:
            return
        cmd = self.joined[1]
        self.joined = None
        self.send_state(PROVISIONED)
        self.result(cmd, self.addresses())

    def scan(self, cmd):
        best = {}
        for ssid, rssi, locked in self.board.scan():
            if ssid and (ssid not in best or rssi > best[ssid][0]):
                best[ssid] = (rssi, locked)
        nets = sorted(best.items(), key=lambda kv: -kv[1][0])[:SCAN_MAX]
        for ssid, (rssi, locked) in nets:
            self.result(cmd, [ssid, str(rssi), "YES" if locked else "NO"])
        self.result(cmd, [])

    def name(self, cmd, fields):
        if fields:
            raw = fields[0].decode()
            from zero_setup import clean_name
            if cmd == HOSTNAME and clean_name(raw) != raw.lower():
                self.send_error(BAD_HOSTNAME)
                return
            if self.board.rename(raw) is None:
                self.send_error(BAD_HOSTNAME if cmd == HOSTNAME else INVALID)
                return
        self.result(cmd, [self.board.name()])


def zero_doc_renamed(doc, name):
    """The board's identity file with its name changed and the rest kept."""
    out = dict(doc) if isinstance(doc, dict) else {}
    out["name"] = name
    return out


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
