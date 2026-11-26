# Map (grep -n a name to jump there):
#   -- Improv over the cable      frame, rpc, wifi_rpc, Frames, result_strings, Improv
#   -- the REPL                   Repl (raw REPL over the Zero's port: files, eval)
#   -- SSH                        Ssh (exec, the client's), Term (a -tt session), free_internal
#   -- the numbers                percentile, rtt, internal_heap, drift, METRICS, zero_record
"""The Zero suite's tools (tests/test_zero_on_glass.py), beside
tests/on_glass.py, which is the console boards'.

A Zero has no dev channel. What the suite asks it over the cable goes two
ways, both on a port opened through `P4Board` (the board's own `[serial]`
line state, exclusive):

  IMPROV, the client side of device/zero_improv.py: the frames the kernel
  takes off the console before the REPL sees them
  (native/moy_kernel/moy_improv.h), each `IMPROV` 0x01 TYPE LEN DATA SUM.

  THE RAW REPL, which Ctrl-C reaches by stopping the store host, and whose
  Ctrl-D (a soft reset) starts it again (the board README's "Hardware
  facts"). Files go both ways as hex inside the exec'd code, so what the
  store holds -- a saved network's password included -- crosses the cable
  and this process's memory only, never a file or a command line.

Over the network the board's shell answers SSH, which the suite reaches with
this machine's OpenSSH client: the password through SSH_ASKPASS from the
client's environment (never a file or a command line), an exec for a
command's bytes and a `-tt` session for what a person types.

The numbers it takes become one perf record (tools/perf_pass.py's `record`)
under the board pass's protocol, which tools/perf_ledger.py sets in its
Zeros table.
"""

import binascii
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "device"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import zero_improv  # noqa: E402 -- the board's side of the protocol

# -- Improv over the cable -----------------------------------------------------

MAGIC = b"IMPROV"
VERSION = 0x01


def frame(kind, data):
    """One frame: the header, the type, the data behind its length, the sum."""
    body = MAGIC + bytes([VERSION, kind, len(data)]) + bytes(data)
    return body + bytes([sum(body) & 0xFF]) + b"\n"


def rpc(cmd, data=b""):
    """An RPC frame: the command, then its data behind its length."""
    return frame(zero_improv.RPC, bytes([cmd, len(data)]) + bytes(data))


def wifi_rpc(ssid, password):
    """The join: the SSID and the password, each behind its length."""
    s, p = ssid.encode(), password.encode()
    return rpc(zero_improv.WIFI, bytes([len(s)]) + s + bytes([len(p)]) + p)


class Frames:
    """The board's bytes, split into its frames [(type, data, sum ok)] and the
    console's other bytes (`other`), across reads that cut either anywhere."""

    def __init__(self):
        self.buf = b""
        self.other = b""
        self.nl = False              # a frame's own newline may come next

    def feed(self, chunk):
        if self.nl and chunk:
            chunk = chunk[1:] if chunk[:1] == b"\n" else chunk
            self.nl = False
        self.buf += chunk
        out = []
        while True:
            at = self.buf.find(MAGIC)
            if at < 0:
                keep = len(self.buf)
                for k in range(len(MAGIC) - 1, 0, -1):
                    if self.buf.endswith(MAGIC[:k]):
                        keep = len(self.buf) - k
                        break
                self.other += self.buf[:keep]
                self.buf = self.buf[keep:]
                return out
            if len(self.buf) < at + 9:
                self.other += self.buf[:at]
                self.buf = self.buf[at:]
                return out
            n = self.buf[at + 8]
            if len(self.buf) < at + 10 + n:
                self.other += self.buf[:at]
                self.buf = self.buf[at:]
                return out
            body = self.buf[at:at + 9 + n]
            ok = self.buf[at + 9 + n] == sum(body) & 0xFF
            self.other += self.buf[:at]
            out.append((self.buf[at + 7], bytes(self.buf[at + 9:at + 9 + n]), ok))
            rest = self.buf[at + 10 + n:]
            self.buf = rest[1:] if rest[:1] == b"\n" else rest
            self.nl = not rest


def result_strings(data):
    """A RESULT frame's data -> (command, [its strings])."""
    got = zero_improv.parse_rpc(data)
    if got is None:
        return None, []
    cmd, fields = got
    return cmd, [f.decode("utf-8", "replace") for f in fields]


class Improv:
    """The client end over a Zero's open port (`ser`: read, write, in_waiting)."""

    def __init__(self, ser):
        self.ser = ser
        self.frames = Frames()

    def _read(self):
        try:
            n = min(self.ser.in_waiting, 4096)
        except Exception:  # noqa: BLE001 -- a fake port
            n = 0
        return self.ser.read(n or 1)

    def ask(self, data, timeout, done):
        """Send `data` (a frame), then collect the board's frames until
        `done(frames)` or `timeout` s: (frames, seconds)."""
        t0 = time.monotonic()
        self.ser.write(data)
        self.ser.flush()
        got = []
        while time.monotonic() - t0 < timeout:
            got += self.frames.feed(self._read())
            if done(got):
                break
        return got, time.monotonic() - t0

    def state(self, timeout=5.0):
        """CURRENT: (state, [urls])."""
        got, _ = self.ask(rpc(zero_improv.CURRENT), timeout, _answered)
        return _state_of(got), _urls_of(got)

    def join(self, ssid, password, timeout=90.0):
        """WIFI: (state, [urls], seconds, error or None); the URLs are the
        RESULT the board sends once it serves on the network it joined."""
        got, secs = self.ask(wifi_rpc(ssid, password), timeout, _joined)
        return _state_of(got), _urls_of(got), secs, _error_of(got)

    def claim(self, timeout=5.0):
        """Moybyte's 0xF0: ([urls], error or None), the first URL's fragment
        a FRESH claim (`#id=<id>&claim=<c>`), minted whether or not the
        board has a password."""
        got, _ = self.ask(rpc(zero_improv.CLAIM), timeout,
                          lambda g: any(k == zero_improv.RESULT for k, d, ok in g)
                          or _error_of(g) is not None)
        return _urls_of(got), _error_of(got)


def _state_of(got):
    states = [d[0] for k, d, ok in got if k == zero_improv.STATE and d]
    return states[-1] if states else None


def _error_of(got):
    errs = [d[0] for k, d, ok in got if k == zero_improv.ERROR and d and d[0]]
    return errs[-1] if errs else None


def _urls_of(got):
    for k, d, ok in got:
        if k == zero_improv.RESULT:
            return result_strings(d)[1]
    return []


def _answered(got):
    return any(k in (zero_improv.RESULT,) for k, d, ok in got) or \
        any(k == zero_improv.STATE and d and d[0] == zero_improv.READY for k, d, ok in got)


def _joined(got):
    """The result, or an error and the state the board falls back to."""
    if any(k == zero_improv.RESULT for k, d, ok in got):
        return True
    errs = [i for i, (k, d, ok) in enumerate(got)
            if k == zero_improv.ERROR and d and d[0]]
    return bool(errs) and any(k == zero_improv.STATE for k, d, ok in got[errs[-1]:])


def bare(url):
    """A URL with its fragment cut: the claim it may carry never prints."""
    return url.split("#", 1)[0]


# -- the REPL ------------------------------------------------------------------

RAW_PROMPT = b"raw REPL; CTRL-B to exit\r\n>"
CHUNK = 1024              # bytes of a file a write carries in one exec


class ReplError(RuntimeError):
    pass


class Repl:
    """The raw REPL on a Zero's open port (`ser`): `enter` stops the store
    host with Ctrl-C, `leave` starts it again with a soft reset."""

    def __init__(self, ser):
        self.ser = ser

    def _until(self, done, timeout, what):
        buf, end = b"", time.monotonic() + timeout
        while time.monotonic() < end:
            n = self.ser.in_waiting
            buf += self.ser.read(min(n, 4096) or 1)
            if done(buf):
                return buf
        raise ReplError("no %s from the board within %.0f s (last: %r)"
                        % (what, timeout, buf[-120:]))

    def enter(self, clean=False, timeout=20.0):
        """Ctrl-C, then the raw REPL. `clean`: a soft reset there too, which
        in the raw REPL starts no main.py, so the code runs on an empty heap
        (the C3's is small, and the stopped host's objects fill it) -- and
        whatever the host served, its sockets included, is gone."""
        for _ in range(3):
            self.ser.write(b"\r\x03")
            self.ser.flush()
            time.sleep(0.3)
        self.ser.reset_input_buffer()
        self.ser.write(b"\r\x01")
        self.ser.flush()
        self._until(lambda b: b.endswith(RAW_PROMPT), timeout, "raw REPL")
        if clean:
            self.clean(timeout)

    def clean(self, timeout=20.0):
        """A soft reset in the raw REPL: an empty heap, no main.py."""
        self.ser.write(b"\x04")
        self.ser.flush()
        self._until(lambda b: b"soft reboot" in b and b.endswith(RAW_PROMPT[-3:]),
                    timeout, "a soft reset in the raw REPL")

    def run(self, code, timeout=30.0):
        """Exec `code`: its stdout, or ReplError with its traceback's last line."""
        self.ser.write(code.encode() + b"\x04")
        self.ser.flush()
        buf = self._until(lambda b: split_reply(b) is not None, timeout, "reply")
        out, err = split_reply(buf)
        if err.strip():
            raise ReplError(err.decode("utf-8", "replace").strip().splitlines()[-1])
        return out.decode("utf-8", "replace")

    def eval(self, expr, timeout=30.0):
        """`expr`'s repr, evaluated on the board, read back with ast."""
        import ast
        out = self.run("print(repr(%s))" % expr, timeout).strip()
        return ast.literal_eval(out)

    def read(self, path):
        """The file's bytes, or None where it does not exist."""
        out = self.run(
            "import binascii\ntry:\n f=open(%r,'rb')\nexcept OSError:\n print('-')\n"
            "else:\n while True:\n  b=f.read(512)\n  if not b: break\n"
            "  print(binascii.hexlify(b).decode())\n f.close()\n print('.')" % path).split()
        if out[:1] == ["-"]:
            return None
        return binascii.unhexlify("".join(out[:-1]))

    def write(self, path, data):
        self.run("f=open(%r,'wb')\nf.close()" % path)
        for at in range(0, len(data), CHUNK):
            self.run("import binascii\nf=open(%r,'ab')\nf.write(binascii.unhexlify(%r))\n"
                     "f.close()" % (path, binascii.hexlify(data[at:at + CHUNK]).decode()))
        size = self.eval("__import__('os').stat(%r)[6]" % path)
        if size != len(data):
            raise ReplError("%s: wrote %d bytes, the board holds %d" % (path, len(data), size))

    def remove(self, path):
        """Remove a file, or a folder and everything in it; nothing where
        there is none."""
        self.run(
            "import os\ndef _rm(p):\n try:\n  m=os.stat(p)[0]\n except OSError:\n  return\n"
            " if m & 0x4000:\n  for n in os.listdir(p):\n   _rm(p+'/'+n)\n  os.rmdir(p)\n"
            " else:\n  os.remove(p)\n_rm(%r)" % path)

    def tree(self, root):
        """{path: size} of every file under `root` (a folder's size -1),
        printed as the board walks it: the C3's heap holds no dict of it."""
        out = self.run(
            "import os, gc\ngc.collect()\ndef _w(p):\n for n in os.listdir(p):\n"
            "  q=p+'/'+n\n  st=os.stat(q)\n  if st[0] & 0x4000:\n   print(-1, q)\n   _w(q)\n"
            "  else:\n   print(st[6], q)\n_w(%r)\ndel _w" % root, timeout=60)
        tree = {}
        for line in out.splitlines():
            size, _, path = line.strip().partition(" ")
            if path:
                tree[path] = int(size)
        return tree

    def mkdirs(self, path):
        self.run("import os\np=''\nfor s in %r.split('/'):\n if s:\n  p+='/'+s\n"
                 "  try:\n   os.mkdir(p)\n  except OSError:\n   pass" % path)

    def put_folder(self, src, dest):
        """A folder of the host's, copied to `dest` on the board."""
        for base, dirs, names in os.walk(src):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            rel = os.path.relpath(base, src)
            there = dest if rel == "." else dest + "/" + rel.replace(os.sep, "/")
            self.mkdirs(there)
            for n in sorted(names):
                with open(os.path.join(base, n), "rb") as f:
                    self.write(there + "/" + n, f.read())

    def leave(self):
        """Out of the raw REPL, and the store host started again."""
        self.ser.write(b"\r\x02")
        self.ser.flush()
        time.sleep(0.3)
        self.ser.write(b"\x04")
        self.ser.flush()


def split_reply(buf):
    """A raw REPL reply (`OK` stdout 0x04 stderr 0x04 `>`) -> (stdout,
    stderr), None while it is not whole."""
    at = buf.find(b"OK")
    if at < 0:
        return None
    parts = buf[at + 2:].split(b"\x04")
    if len(parts) < 3 or not parts[2].startswith(b">"):
        return None
    return parts[0], parts[1]


INTERNAL_HEAP = 0x800      # MALLOC_CAP_INTERNAL, esp32.idf_heap_info's caps


def internal_heap(regions):
    """(free, largest) bytes of esp32.idf_heap_info(MALLOC_CAP_INTERNAL)'s
    [(total, free, largest, min_free)]."""
    regions = [r for r in regions if r]
    return sum(r[1] for r in regions), max((r[2] for r in regions), default=0)


# -- SSH -------------------------------------------------------------------------

ASKPASS = "#!/bin/sh\necho \"$MOY_SSH_PW\"\n"


class Ssh:
    """This machine's OpenSSH client against a board's shell at `host`,
    signed in with `password` through SSH_ASKPASS; `home` a folder of its
    own (the askpass script, and HOME, so no key or config of this user's
    is offered)."""

    def __init__(self, host, password, home, port=22):
        self.host, self.port = host, port
        self.password = password
        self.home = home
        os.makedirs(home, exist_ok=True)
        self.askpass = os.path.join(home, "askpass.sh")
        with open(self.askpass, "w") as f:
            f.write(ASKPASS)
        os.chmod(self.askpass, 0o700)

    def argv(self, *args, tty=False):
        return ["ssh", "-F", "/dev/null", "-p", str(self.port), "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR",
                "-o", "NumberOfPasswordPrompts=1", "-o", "PubkeyAuthentication=no",
                "-o", "PreferredAuthentications=password", "-o", "ConnectTimeout=15"] + \
            (["-tt"] if tty else []) + ["moy@" + self.host] + list(args)

    def env(self):
        return dict(os.environ, SSH_ASKPASS=self.askpass, SSH_ASKPASS_REQUIRE="force",
                    DISPLAY="moy", MOY_SSH_PW=self.password or "", HOME=self.home)

    def run(self, command, stdin=b"", timeout=120):
        """An exec: (exit status, stdout bytes, stderr bytes)."""
        import subprocess
        r = subprocess.run(self.argv(command), env=self.env(), input=stdin,
                           capture_output=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr

    def term(self):
        return Term(self)


class Term:
    """A `-tt` session: keys sent as a person types them, the screen's bytes
    gathered as they come (a reader thread), `expect` waiting for a pattern
    after a mark."""

    def __init__(self, ssh):
        import subprocess
        import threading
        self.proc = subprocess.Popen(ssh.argv(tty=True), env=ssh.env(),
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT)
        self.buf = b""
        self.lock = threading.Lock()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        while True:
            b = self.proc.stdout.read1(4096)
            if not b:
                return
            with self.lock:
                self.buf += b

    def mark(self):
        with self.lock:
            return len(self.buf)

    def since(self, at):
        with self.lock:
            return self.buf[at:]

    def send(self, data, wait=0.0):
        self.proc.stdin.write(data)
        self.proc.stdin.flush()
        if wait:
            time.sleep(wait)

    def expect(self, pattern, at=0, timeout=30.0):
        """The match of regex `pattern` (bytes) in what came after `at`, or
        None when it did not come within `timeout` s or the session ended."""
        rx = re.compile(pattern, re.S)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            m = rx.search(self.since(at))
            if m:
                return m
            if self.proc.poll() is not None:
                return rx.search(self.since(at))
            time.sleep(0.05)
        return None

    def command(self, line, timeout=60.0):
        """`line` typed and Enter: what it printed before the prompt came
        back (the prompt's line not in it), or None."""
        at = self.mark()
        self.send(line.encode() + b"\r")
        m = self.expect(re.escape(line.encode()) + rb"\r\n(.*?)(?:\r\n)?[^\r\n]*\$ $",
                        at, timeout)
        return m.group(1) if m else None

    def alive(self):
        return self.proc.poll() is None

    def close(self):
        if self.proc.poll() is None:
            try:
                self.send(b"\x03exit\r", 0.5)
            except OSError:
                pass
        try:
            self.proc.wait(timeout=10)
        except Exception:  # noqa: BLE001 -- a session that will not end is killed
            self.proc.kill()
            self.proc.wait(timeout=10)


def free_internal(text):
    """`free`'s internal row -> (total, used, free) bytes, None without one."""
    for line in text.splitlines():
        f = line.split()
        if len(f) == 4 and f[0] == "internal":
            return tuple(int(x) for x in f[1:])
    return None


# -- the numbers ---------------------------------------------------------------

def percentile(xs, p):
    """The `p`th percentile of `xs` (nearest rank), None of none."""
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    if not xs:
        return None
    import math
    k = max(0, min(len(xs) - 1, math.ceil(p / 100.0 * len(xs)) - 1))
    return xs[k]


def rtt(samples):
    """(median, p90) ms of the live socket's echo round trips."""
    return percentile(samples, 50), percentile(samples, 90)


def drift(samples, band):
    """How far `samples` (one figure a round, the first the baseline) fell:
    (the drop of the last rounds' best from the first, whether it is past
    `band`). The best of the last three, so one round caught mid-request
    is not a leak, and a figure that keeps falling is."""
    if len(samples) < 2:
        return 0, False
    drop = samples[0] - max(samples[-3:])
    return drop, drop > band


# Each metric's unit and direction, the ledger's Zeros rows in this order.
METRICS = (
    ("zero internal free idle", "KiB", "higher"),
    ("zero internal largest idle", "KiB", "higher"),
    ("zero internal free live", "KiB", "higher"),
    ("zero internal largest live", "KiB", "higher"),
    ("zero live rtt median", "ms", "lower"),
    ("zero live rtt p90", "ms", "lower"),
    ("zero improv join", "ms", "lower"),
    ("zero page root", "ms", "lower"),
    ("zero page sync", "ms", "lower"),
    ("zero page reload boot", "ms", "lower"),
    ("zero claim to live", "ms", "lower"),
)


def zero_record(board, taken, errors, image, secs=None):
    """The suite's numbers as one perf record. `taken`: {name: (value,
    samples)}; a metric the run did not take is None, and `errors` says why."""
    import perf_pass
    metrics = {}
    for name, unit, better in METRICS:
        value, samples = taken.get(name, (None, ()))
        metrics[name] = perf_pass.metric(value, unit, better, samples)
    errors = dict(errors)
    for name, _unit, _better in METRICS:
        if metrics[name]["value"] is None and name not in errors:
            errors[name] = "not taken (its test did not run)"
    stamp = (image or {}).get("stamp") or "?"
    return perf_pass.record(board, metrics, stamp, image=image, secs=secs,
                            errors=errors,
                            protocol=perf_pass.protocol(perf_pass.AFTER_SUITE))
