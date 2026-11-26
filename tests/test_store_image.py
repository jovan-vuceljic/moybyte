"""The website's install image (tools/store_image.py): each board's merged
image, then its internal store holding the browser console add-on that fits.

What is pinned: the store sits where each board's table and chip put it (the
"vfs" partition, or MicroPython's tail on the P4s); the bytes between the
image and the store are erased flash; and the store is a LittleFS that the
desktop MicroPython's VfsLfs2 -- the same littlefs, on-disk shape and block
size as every board's internal store (native/moy_store/moy_kvfs.c) -- mounts
at the partition's whole size, with the add-on's pack and manifest read back
whole, junk past the image left as free space, and room to write after."""

import hashlib
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from unix_mp import require_unix_mp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

pytest.importorskip("littlefs", reason="littlefs-python is the dev extra's (make setup)")

import board_config  # noqa: E402
import gen_web_blob  # noqa: E402
import store_image  # noqa: E402
import web_pack  # noqa: E402

# Each board: its folder, the store's offset and size its table and chip give.
BOARDS = {
    "tdeck": ("lilygo_t_deck_plus_mainline", 0xC60000, 0x3A0000),
    "guition_s3": ("guition_jc3248w535", 0xC60000, 0x3A0000),
    "p4": ("esp32_p4_wifi6_touch_lcd_7b", 0xD50000, (32 << 20) - 0xD50000),
    "guition_p4": ("guition_jc8012p4a1c", 0xD50000, (16 << 20) - 0xD50000),
    "elecrow_p4": ("elecrow_crowpanel_p4_10_1", 0xD50000, (16 << 20) - 0xD50000),
    "xiao_zero": ("seeed_xiao_esp32s3_zero", 0x500000, 0x300000),
    "c3_zero": ("esp32c3_zero", 0x1F0000, 0x210000),
}
SIZES = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4, 32: 5}
TYPES = {"app": 0, "data": 1}
SUBTYPES = {"factory": 0, "ota_0": 0x10, "ota_1": 0x11, "ota": 0, "phy": 1, "nvs": 2,
            "coredump": 3, "fat": 0x81}


def _board(name):
    return ROOT / "firmware" / BOARDS[name][0]


def _csv(board):
    rows = []
    for path in (board / "boards").glob("*/partitions-*.csv"):
        for line in path.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                rows.append([f.strip() for f in line.split(",")])
    return rows


def _flash_mb(board):
    for path in (board / "boards").glob("*/sdkconfig.board"):
        m = re.search(r"^CONFIG_ESPTOOLPY_FLASHSIZE_(\d+)MB=y$", path.read_text(), re.M)
        if m:
            return int(m.group(1))
    return 4                                  # the port's default


def _merged(board, offset, app=b"app" * 1000):
    """A merged image as MicroPython's makeimg writes one: the bootloader's
    header naming the chip size, the table from the board's CSV at 0x8000,
    the app at the first app partition, 0xFF between."""
    rows = _csv(board)
    table = bytearray()
    for name, kind, sub, off, size in (r[:5] for r in rows):
        table += struct.pack("<HBBII16sI", 0x50AA, TYPES[kind], SUBTYPES.get(sub) if sub in SUBTYPES else int(sub, 0),
                             int(off, 0), int(size, 0), name.encode(), 0)
    table += b"\xeb\xeb" + b"\xff" * 14 + hashlib.md5(table).digest()
    app_at = min(int(r[3], 0) for r in rows if r[1] == "app")
    img = bytearray(b"\xff" * (app_at - offset))
    img[0:4] = bytes((0xE9, 3, 2, (SIZES[_flash_mb(board)] << 4) | 0xF))
    t = store_image.TABLE_AT - offset
    img[t:t + len(table)] = table
    return bytes(img) + app


def _pack(tag=b"x"):
    return gen_web_blob.pack_bytes([("index.html.gz", b"\x1f\x8b" + tag * 5000),
                                    ("micropython.wasm.gz", bytes(range(256)) * 900)])


@pytest.mark.parametrize("name", sorted(BOARDS))
def test_the_store_is_where_each_board_mounts_it(name):
    board = _board(name)
    offset = int(str(board_config.load(board)["flash"]["offset"]), 0)
    merged = _merged(board, offset)
    assert store_image.store_part(merged, offset) == BOARDS[name][1:]


@pytest.mark.parametrize("name", sorted(BOARDS))
def test_a_board_s_sources_lay_the_store_its_image_carries(name):
    """The check reads a board's store from its partition CSV and sdkconfig
    (`board_store`), where the install reads it from the image they build."""
    board = _board(name)
    offset = int(str(board_config.load(board)["flash"]["offset"]), 0)
    assert store_image.board_store(str(board)) == store_image.store_part(_merged(board, offset), offset)


def _wasm_pack(size):
    import random
    body = random.Random(size).randbytes(size)
    return gen_web_blob.pack_bytes([("micropython.wasm.gz", body)])[0]


def test_the_check_fails_a_pack_that_outgrows_a_board_s_store():
    """Every board with a store is checked, and a pack whose add-on does not
    fit one fails it."""
    import io
    assert sorted(os.path.basename(d) for d in store_image.board_dirs()) == sorted(b[0] for b in BOARDS.values())
    out = io.StringIO()
    assert store_image.check(_wasm_pack(1 << 20), out) == [], out.getvalue()
    p4 = str(_board("guition_p4"))
    blocks = store_image.board_store(p4)[1] // store_image.BLOCK
    out = io.StringIO()
    assert store_image.check(_wasm_pack((blocks + 1) * store_image.BLOCK), out) == [
        "elecrow_crowpanel_p4_10_1", "guition_jc8012p4a1c"]
    assert "do not fit a store of %d blocks" % blocks in out.getvalue()


ONLINE = ("c3_zero", "xiao_zero")      # the Zeros (owner, 2026-11-23 and 2026-11-26)


@pytest.mark.parametrize("name", ONLINE)
def test_a_board_whose_console_is_online_gets_no_add_on(tmp_path, name):
    """A Zero's console is online (`[web] console`): its install's store
    holds no add-on, and the check holds its store to its first boot's
    carts and the seed's reserve alone, whatever the pack."""
    import io
    c3 = _board(name)
    assert board_config.web_console(c3) == "online"
    assert set(board_config.web_console(_board(n)) for n in BOARDS if n not in ONLINE) == {"addon"}
    toml = tmp_path / "board.toml"
    toml.write_text('[web]\nconsole = "cloud"\n')
    with pytest.raises(ValueError, match="console must be one of addon, online"):
        board_config.web_console(tmp_path)
    offset = int(str(board_config.load(c3)["flash"]["offset"]), 0)
    merged = _merged(c3, offset)
    out = store_image.install_image(merged, offset, None)
    at, size = BOARDS[name][1:]
    assert out[:len(merged)] == merged and len(out) - (at - offset) <= 8 * store_image.BLOCK
    blocks, addon, both = store_image.room(str(c3), None)
    assert blocks - both >= store_image.seed_reserve() // store_image.BLOCK
    text = io.StringIO()
    folder = BOARDS[name][0]
    assert folder not in store_image.check(_wasm_pack(size + 4096), text)
    assert "%-28s store  %d blocks, no add-on: its console is online" % (
        folder, size // store_image.BLOCK) in text.getvalue()


def test_the_c3_s_install_holds_its_roster_s_carts_and_no_pin_light():
    """The C3's install writes `[roster] install` into its new store (the
    apps and Brick Siege its image has no room for), each folder as an
    official entry installs it, and no Pin Light (owner, 2026-11-24)."""
    from littlefs import LittleFS
    c3 = _board("c3_zero")
    offset = int(str(board_config.load(c3)["flash"]["offset"]), 0)
    merged = _merged(c3, offset)
    carts = store_image.installs(c3)
    out = store_image.install_image(merged, offset, None, carts)
    at, size = BOARDS["c3_zero"][1:]
    store = out[at - offset:]
    fs = LittleFS(block_size=store_image.BLOCK, block_count=size // store_image.BLOCK,
                  read_size=store_image.READ, prog_size=store_image.PROG,
                  lookahead_size=store_image.LOOKAHEAD, cache_size=store_image.CACHE,
                  block_cycles=store_image.CYCLES, mount=False)
    fs.context.buffer = bytearray(store) + bytearray(b"\xff" * (size - len(store)))
    fs.mount()
    want = ["moybyte.%s.moy" % c for c in
            ("brick_siege", "calc", "music", "my_art", "notes", "terminal")]
    assert sorted(fs.listdir(store_image.CARTS)) == want
    for folder in want:
        src = ROOT / "system_carts" / folder / "manifest.json"
        with fs.open("%s/%s/manifest.json" % (store_image.CARTS, folder), "rb") as f:
            assert f.read() == src.read_bytes()
    blocks, _addon, both = store_image.room(str(c3), None)
    assert blocks - both >= store_image.seed_reserve() // store_image.BLOCK


@pytest.mark.parametrize("name", sorted(BOARDS))
def test_each_board_s_internal_carts_folder_is_the_one_the_image_fills(name):
    """The add-on lands in /moy/carts, the carts folder every board's
    internal store keeps (a console's moy_runtime, a Zero's board.toml)."""
    board = _board(name)
    flash = board_config.load(board)["flash"]
    if "addon" in flash:
        assert flash["addon"] == store_image.CARTS
        return
    text = (board / "modules" / "moy_runtime.py").read_text()
    assert re.search(r'^(FLASH_)?CARTS_ROOT = "%s"$' % store_image.CARTS, text, re.M)


def test_the_add_on_s_folder_names_agree_everywhere():
    from runtime import moy_seed, web_addon
    page_h = (ROOT / "native/moy_net/moy_page.h").read_text()
    removed_h = (ROOT / "native/moy_store/moy_removed.h").read_text()
    prefix = web_pack.CART_ID % ""
    assert '#define MOY_PAGE_CART "%s"' % prefix in page_h
    assert '#define MOY_REMOVED_ADDON_CART "%s"' % prefix in removed_h
    assert '#define MOY_REMOVED_ADDON "%s"' % moy_seed.ADDON_LINE in removed_h
    assert web_addon.PREFIX == moy_seed.ADDON_PREFIX == prefix


@pytest.mark.parametrize("name", ["c3_zero", "p4"])
def test_the_install_is_the_image_then_the_store(name):
    board = _board(name)
    offset = int(str(board_config.load(board)["flash"]["offset"]), 0)
    merged = _merged(board, offset)
    pack, _digest = _pack()
    out = store_image.install_image(merged, offset, pack)
    at = BOARDS[name][1] - offset
    assert out[:len(merged)] == merged
    assert set(out[len(merged):at]) == {0xFF}
    assert len(out) - at < len(pack) + 64 * 4096, "the store's used blocks only"


MOUNT = r'''
import os, vfs, json
img = open(@IMG@, "rb").read()
N = @BLOCKS@


class Flash:
    """The partition: the image's blocks, junk past them (an old store), and
    what the session writes."""
    def __init__(self):
        self.w = {}

    def _block(self, b):
        if b in self.w:
            return self.w[b]
        if b * 4096 < len(img):
            return img[b * 4096:(b + 1) * 4096]
        return bytes([0x5A, b & 0xFF]) * 2048

    def readblocks(self, b, buf, off=0):
        n = len(buf)
        at = 0
        while at < n:
            blk = bytearray(self._block(b + (off + at) // 4096))
            o = (off + at) % 4096
            k = min(n - at, 4096 - o)
            buf[at:at + k] = blk[o:o + k]
            at += k

    def writeblocks(self, b, buf, off=None):
        off = off or 0
        at = 0
        while at < len(buf):
            i = b + (off + at) // 4096
            o = (off + at) % 4096
            k = min(len(buf) - at, 4096 - o)
            blk = bytearray(self._block(i))
            blk[o:o + k] = buf[at:at + k]
            self.w[i] = bytes(blk)
            at += k

    def ioctl(self, op, arg):
        if op == 4:
            return N
        if op == 5:
            return 4096
        if op == 6:
            self.w[arg] = b"\xff" * 4096
        return 0


vfs.mount(vfs.VfsLfs2(Flash()), "/s")
st = os.statvfs("/s")
print("BLOCKS", st[2], st[3])
carts = "/s/moy/carts"
names = os.listdir(carts)
print("CARTS", json.dumps(names))
cart = carts + "/" + names[0]
print("FILES", json.dumps(sorted(os.listdir(cart))))
with open(cart + "/manifest.json") as f:
    print("FITS", json.loads(f.read())["moybyte"]["fits"])
with open(cart + "/moybyte_web.pack", "rb") as f:
    head = f.read(48)
    size = 48
    while True:
        b = f.read(4096)
        if not b:
            break
        size += len(b)
print("HEAD", head[:8].decode(), head[16:48].hex(), size)
with open("/s/moy/written", "wb") as f:
    f.write(b"k" * 100000)
print("WROTE", os.stat("/s/moy/written")[6])
'''


@pytest.mark.parametrize("name", sorted(BOARDS))
def test_each_board_s_store_mounts_in_micropython_with_the_add_on(name, tmp_path):
    exe = require_unix_mp(why="the only check that the store image is the "
                              "LittleFS a board's MicroPython mounts")
    board = _board(name)
    offset = int(str(board_config.load(board)["flash"]["offset"]), 0)
    merged = _merged(board, offset)
    pack, digest = _pack(name.encode())
    out = store_image.install_image(merged, offset, pack)
    at, size = BOARDS[name][1:]
    img = tmp_path / "store.bin"
    img.write_bytes(out[at - offset:])
    script = tmp_path / "mount.py"
    script.write_text(MOUNT.replace("@IMG@", repr(str(img)))
                      .replace("@BLOCKS@", str(size // 4096)))
    run = subprocess.run([exe, "-X", "heapsize=32m", str(script)],
                         capture_output=True, text=True, timeout=300)
    lines = dict(ln.split(" ", 1) for ln in run.stdout.splitlines() if " " in ln)
    assert run.returncode == 0, run.stdout + run.stderr
    total, free = map(int, lines["BLOCKS"].split())
    assert total == size // 4096
    assert free > total - len(pack) // 4096 - 32, "the junk past the image is free space"
    folder = web_pack.cart_id(digest.hex()) + ".moy"
    assert json.loads(lines["CARTS"]) == [folder]
    assert json.loads(lines["FILES"]) == ["LICENSE.md", "manifest.json", "moybyte_web.pack"]
    assert lines["FITS"] == digest.hex()
    assert lines["HEAD"] == "MOYWEB01 %s %d" % (digest.hex(), len(pack))
    assert lines["WROTE"] == "100000"
