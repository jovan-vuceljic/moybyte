"""The card volume (native/moy_store/moy_card.c: FatFS over the sector cache)
through every way a raw upload ends, on the desktop MicroPython: the dev
channel's `recv` (a `.new` written window by window, then renamed over its
file, or closed and removed when the board times out or the host's hash
disagrees), carts made and removed beside it, while a task of no VM
(moy_store.task: publish, read, rename, list, what the saver does) works the
same volume. The medium is then walked here, FAT and directories, as
fsck.fat would: no cluster in two chains, no chain into a free cluster, no
entry whose name is not one FatFS writes, no allocated cluster nobody owns.

A card that refuses writes for a moment (moy_sd's error, a Python driver's
non-zero return) may leave space nobody owns and a long name with no entry,
as a power cut there would; it never leaves two owners of one cluster or a
directory of garbage."""

import struct
import subprocess

from unix_mp import require_unix_mp

SECTORS = 65536
SMALL = 16384                           # the refusing card: a Python driver, its medium on the heap

SCRIPT = """
import os, vfs, random, hashlib, moy_store
random.seed(@SEED@)
def rm(p):
    try: os.remove(p)
    except OSError: pass
def mk(p):
    try: os.mkdir(p)
    except OSError: pass
def uploads(C, steps, d=None):
    dst = C + "/_baudtest.bin"; tmp = dst + ".new"
    refused = 0
    for step in range(steps):
        kind = random.choice(("ok", "ok", "timeout", "mismatch", "cart", "rmcart")
                             + (("refused",) if d else ()))
        if kind == "cart":
            f = "%s/moybyte.extra_%d.moy" % (C, random.randint(0, 9)); mk(f)
            with open(f + "/main.wasm", "wb") as o: o.write(os.urandom(random.randint(10, 9000)))
            continue
        if kind == "rmcart":
            for n in os.listdir(C):
                if n.startswith("moybyte.extra_"):
                    for m in os.listdir(C + "/" + n): os.remove(C + "/" + n + "/" + m)
                    os.rmdir(C + "/" + n)
                    break
            continue
        total = 3072 * random.randint(1, 40)
        data = os.urandom(total)
        stop = random.randint(0, total) if kind in ("timeout", "refused") else total
        if kind == "refused":
            d.fail_at = d.n + random.randint(1, 30); d.burst = random.randint(1, 3)
        err = None
        f = open(tmp, "wb")
        try:
            got = 0
            while got < stop:
                n = min(3072, stop - got); f.write(data[got:got + n]); got += n
        except OSError as e:
            err = e
        try:
            f.close()
        except OSError as e:
            err = err or e
        if d:
            d.fail_at = -1
        refused += err is not None
        if err is not None or kind != "ok":
            rm(tmp); continue
        rm(dst); os.rename(tmp, dst)
        with open(dst, "rb") as f:
            assert hashlib.sha256(f.read()).digest() == hashlib.sha256(data).digest(), step
        rm(dst)
    return refused
def seed(C):
    for p in ("/sd/moybyte", C, "/sd/moybyte/apps"):
        mk(p)
    for i in range(20):
        f = "%s/moybyte.seed_cart_number_%02d.moy" % (C, i)
        mk(f)
        with open(f + "/manifest.json", "w") as o: o.write("x" * random.randint(5, 3000))

vfs.mount(moy_store.card_ram(@SECTORS@), "/sd")
seed("/sd/moybyte/carts")
moy_store.task("/sd/moybyte/apps", 200)
uploads("/sd/moybyte/carts", 40)
ok, at, rc, refused = moy_store.task_join()
assert (at, rc, refused) == (-1, 0, 0), (ok, at, rc, refused)
vfs.umount("/sd")
with open("@OUT@.task", "wb") as o:
    o.write(moy_store.card_ram())

class Card:
    def __init__(self, image):
        self.disk = bytearray(image); self.n = 0; self.fail_at = -1; self.burst = 0
    def read(self, block, buf, n):
        buf[:] = memoryview(self.disk)[block * 512:(block + n) * 512]
    def write(self, block, buf, n):
        self.n += 1
        if self.fail_at >= 0 and self.fail_at <= self.n < self.fail_at + self.burst:
            return 5
        memoryview(self.disk)[block * 512:(block + n) * 512] = buf
moy_store.card_ram(@SMALL@)
d = Card(moy_store.card_ram())
vfs.mount(moy_store.card(@SMALL@, d), "/sd")
seed("/sd/moybyte/carts")
refused = uploads("/sd/moybyte/carts", 60, d)
vfs.umount("/sd")
with open("@OUT@.refused", "wb") as o:
    o.write(d.disk)
print("done", refused)
"""

SFN_OK = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 !#$%&'()-@^_`{}~") | set(range(0x80, 0x100))


def check(img):
    """(problems, lost): what fsck.fat would repair beyond lost space, and the
    clusters allocated that no entry reaches."""
    bps, spc, rsv, nf = struct.unpack_from("<HBHB", img, 11)
    root_ents = struct.unpack_from("<H", img, 17)[0]
    total = struct.unpack_from("<H", img, 19)[0] or struct.unpack_from("<I", img, 32)[0]
    fatsz = struct.unpack_from("<H", img, 22)[0] or struct.unpack_from("<I", img, 36)[0]
    root_at = rsv + nf * fatsz
    data_at = root_at + (root_ents * 32 + bps - 1) // bps
    ncl = (total - data_at) // spc + 2
    bits = 12 if ncl < 4087 else 16 if ncl < 65527 else 32
    fat0 = rsv * bps

    def fat(c):
        if bits == 12:
            v = struct.unpack_from("<H", img, fat0 + c + c // 2)[0]
            return v >> 4 if c & 1 else v & 0xFFF
        if bits == 16:
            return struct.unpack_from("<H", img, fat0 + c * 2)[0]
        return struct.unpack_from("<I", img, fat0 + c * 4)[0] & 0x0FFFFFFF

    eoc = {12: 0xFF8, 16: 0xFFF8, 32: 0x0FFFFFF8}[bits]
    problems, owner = [], {}

    def chain(c, who):
        out = []
        while True:
            if not 2 <= c < ncl:
                problems.append("%s: chain leaves the volume at %d" % (who, c))
                return out
            if c in owner:
                problems.append("%s: cluster %d is also %s's" % (who, c, owner[c]))
                return out
            v = fat(c)
            if v == 0:
                problems.append("%s: chain runs into free cluster %d" % (who, c))
                return out
            owner[c] = who
            out.append(c)
            if v >= eoc:
                return out
            c = v

    def clusters(cs):
        return b"".join(img[(data_at + (c - 2) * spc) * bps:(data_at + (c - 1) * spc) * bps] for c in cs)

    def walk(raw, path):
        for i in range(0, len(raw), 32):
            e = raw[i:i + 32]
            if e[0] == 0:
                return
            if e[0] == 0xE5 or e[11] == 0x0F or e[:2] in (b". ", b".."):
                continue
            name = path + "/" + e[:11].decode("latin1")
            if e[11] & 0xC0 or not set(e[:11]) <= SFN_OK:
                problems.append("%r: not a name FatFS writes" % name)
                continue
            c = struct.unpack_from("<H", e, 26)[0]
            if bits == 32:
                c |= struct.unpack_from("<H", e, 20)[0] << 16
            if c:
                cs = chain(c, name)
                if e[11] & 0x10:
                    walk(clusters(cs), name)

    if bits == 32:
        walk(clusters(chain(struct.unpack_from("<I", img, 44)[0], "/")), "")
    else:
        walk(img[root_at * bps:data_at * bps], "")
    lost = [c for c in range(2, ncl) if fat(c) not in (0, eoc - 1) and c not in owner]
    return problems, lost


def test_every_way_an_upload_ends_leaves_the_card_whole(tmp_path):
    exe = require_unix_mp("moy_store", why="the card volume under the upload's abort paths")
    for s in range(3):
        out = tmp_path / ("card%d" % s)
        script = tmp_path / ("aborts%d.py" % s)
        script.write_text(SCRIPT.replace("@SEED@", str(s)).replace("@SECTORS@", str(SECTORS))
                          .replace("@SMALL@", str(SMALL))
                          .replace("@OUT@", str(out)))
        done = subprocess.run([exe, "-X", "heapsize=48M", str(script)], capture_output=True,
                              text=True, timeout=300)
        assert done.returncode == 0 and done.stdout.startswith("done "), done.stdout + done.stderr
        assert int(done.stdout.split()[1]) > 0      # the card did refuse an upload's writes
        problems, lost = check((tmp_path / ("card%d.task" % s)).read_bytes())
        assert (problems, lost) == ([], []), s
        problems, _ = check((tmp_path / ("card%d.refused" % s)).read_bytes())
        assert problems == [], s


STALE = """
import os, vfs, moy_store
class Card:
    def __init__(self, image): self.disk = bytearray(image); self.refuse = False
    def read(self, b, buf, n): buf[:] = memoryview(self.disk)[b * 512:(b + n) * 512]
    def write(self, b, buf, n):
        if self.refuse: return 5
        memoryview(self.disk)[b * 512:(b + n) * 512] = buf
moy_store.card_ram(@SMALL@)
d = Card(moy_store.card_ram())
vfs.mount(moy_store.card(@SMALL@, d), "/sd")
C = "/sd/carts"
os.mkdir(C)
for i in range(3):
    os.mkdir(C + "/moybyte.seed_cart_%d.moy" % i)
tmp = C + "/_baudtest.bin.new"
f = open(tmp, "wb")
f.write(os.urandom(5000))
d.refuse = True
try:
    f.close()
    print("closed")
except OSError:
    print("refused")
d.refuse = False
os.remove(tmp)
with open(C + "/moybyte.new_cart_from_get_carts.moy.new", "wb") as g:
    g.write(os.urandom(9000))
try:
    f.close()                   # what its finaliser does at the next collection
except OSError:
    pass
print(sorted(os.listdir(C)))
vfs.umount("/sd")
with open("@OUT@", "wb") as o:
    o.write(d.disk)
"""


def test_a_close_the_card_refused_is_final(tmp_path):
    """The dev channel's `recv` closes its `.new` and removes it when the
    upload fails, as Get Carts does its `.part`. A close the card refused left
    the file open in stock VfsFat, and its finaliser closed it again later --
    after the next upload's long name had taken its directory slot, which then
    listed as garbage (tools/patch_fatfs_close.py)."""
    exe = require_unix_mp("moy_store", why="a refused close on the card volume")
    script = tmp_path / "stale.py"
    out = tmp_path / "stale.img"
    script.write_text(STALE.replace("@SMALL@", str(SMALL)).replace("@OUT@", str(out)))
    done = subprocess.run([exe, "-X", "heapsize=32M", str(script)], capture_output=True,
                          text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
    lines = done.stdout.splitlines()
    assert lines[0] == "refused", lines
    assert lines[1] == str(['moybyte.new_cart_from_get_carts.moy.new', 'moybyte.seed_cart_0.moy',
                            'moybyte.seed_cart_1.moy', 'moybyte.seed_cart_2.moy']), lines
    problems, _ = check(out.read_bytes())
    assert problems == []
