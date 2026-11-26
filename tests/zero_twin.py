"""The store host's twin, run by the board model's MicroPython
(tests/test_zero_heap.py): `zero_host.start()` as a board runs it, over the
kernel's own webhost on a real socket, in the Python heap a C3 has.

argv: runtime tree, device tree, a JSON file of what Twin writes
(tests/test_zero_heap.py). The store is `moy/` under the working directory. A line
on stdin is answered with the heap as it stands after a collect: `HEAP <line>
<free> <used> <modules imported since start>`, then mem_info's own lines.

What a board has and this process lacks is stood in for here and nowhere
else: the radio (Radio), the join (`connect`), the release keys an index is
checked against, and the browser console, which this store does not hold.
"""
import sys

sys.path[:0] = [sys.argv[1], sys.argv[2]]

import gc                           # noqa: E402
import json                         # noqa: E402
import select                       # noqa: E402
import time                         # noqa: E402

import micropython                  # noqa: E402

import cart_index                   # noqa: E402
import moy_webhost                  # noqa: E402
import zero_host                    # noqa: E402
import zero_setup                   # noqa: E402
import zero_wifi                    # noqa: E402

CONF = json.load(open(sys.argv[3]))


class Radio:
    """A station joined to `bench`, in a street of forty networks."""

    def wifi_status(self):
        return (1, 0, True, "bench", "127.0.0.1", 0)

    def wifi_scan(self, block):
        return [(("street %02d" % i).encode(), -40 - i, 3) for i in range(40)]

    def wifi_forget(self, ssid):
        pass


def main():
    zero_host.connect = lambda **kw: "127.0.0.1"
    zero_host.make_wifi = lambda name: zero_wifi.ZeroWifi(zero_host.WIFI_STORE, name,
                                                         radio=Radio())
    zero_host._ZeroWifi.status = lambda self: (True, "bench", "127.0.0.1")
    zero_host.console_online = lambda: True     # no add-on to fetch: the page is elsewhere
    for name in ("ROOT", "CARTS_DIR", "WIFI_STORE", "ZERO_STORE", "SYSTEM_DIR", "UPDATE_DIR"):
        setattr(zero_host, name, getattr(zero_host, name)[1:])      # under the working directory
    if CONF.get("step") is not None:
        zero_host.GC_STEP = CONF["step"]
    zero_wifi.NETS_HOLD_MS = CONF["hold_ms"]      # a round here is seconds, not a visit
    cart_index.INDEX_KEYS = tuple((k[0], k[1]) for k in CONF["keys"])
    moy_webhost.DEFAULT_PORT = CONF["port"]
    for d in (zero_host.ROOT, zero_host.SYSTEM_DIR, zero_host.UPDATE_DIR):
        zero_host._mkdir(d)
    with open(zero_host.SYSTEM_DIR + "/password", "w") as f:
        f.write(zero_setup.console_hash(CONF["password"]))
    with open(zero_host.SYSTEM_DIR + "/sources", "w") as f:
        f.write(CONF["shelf"] + "\n")
    with open(zero_host.UPDATE_DIR + "/ota.json", "w") as f:
        json.dump({"manifest_url": CONF["manifest"]}, f)

    turn = zero_host.start()
    started = sorted(sys.modules)
    gc.collect()
    # The heap a C3 has left once its host is up: a chain of small blocks
    # takes the rest of this one, lowest first, so what is free is one run at
    # the top, as it is there.
    ballast = None
    while gc.mem_free() > CONF["free"] + 256:
        ballast = (bytearray(200), ballast)

    waiting = select.poll()
    waiting.register(sys.stdin, select.POLLIN)
    print("READY")
    while True:
        turn()
        if waiting.poll(0):
            line = sys.stdin.readline().strip()
            if not line or line == "quit":
                return ballast
            gc.collect()
            print("HEAP", line, gc.mem_free(), gc.mem_alloc(),
                  " ".join(m for m in sorted(sys.modules) if m not in started) or "-")
            micropython.mem_info()
            print("END", line)
        time.sleep_ms(1)


main()
