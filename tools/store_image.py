#!/usr/bin/env python3
# Map (grep -n a name to jump there):
#   partitions      the partition table a merged image carries
#   flash_bytes     the flash size its bootloader's header names
#   store_part      the internal store's offset and size: "vfs", else MicroPython's tail
#   board_store     the same from a board's sources: the partition CSV and chip its sdkconfig names
#   store_image     a LittleFS image of the store holding given files, its used blocks only
#   install_image   bootloader + table + app + the store with the browser console add-on
#   install_name    the install image's file name beside the merged one
#   first_boot      the carts a new store takes beside the add-on
#   room            a board's store against a pack: what the add-on and its first boot leave
#   check           every board's room for the bundle built: the add-on, and on a Zero its first boot
"""The website's install of a board: its merged image (bootloader, partition
table, app) and, at the internal store's offset, a store holding the browser
console add-on that fits the app (tools/web_pack.py), and nothing else -- the
image seeds its own carts on its first boot.

    python3 tools/store_image.py firmware/<board>        # dist/<board>/<stem>_install.bin
    python3 tools/store_image.py firmware/<board> --out x.bin
    python3 tools/store_image.py --check [--pack PACK]   # every board's store against the bundle

Written at the merged image's offset (board.toml's `[flash] offset`), it
replaces the board's internal store: the store's first blocks become a new
LittleFS, and what lay past them is free space to it. A card is not touched;
a board whose carts live on a card moves the add-on there on its first boot
(moy_seed.bring_addon).

THE STORE is the kernel's LittleFS over the "vfs" partition (native/moy_store/
moy_kvfs.c, the same on-disk shape as MicroPython's VfsLfs2 on every board):
4096-byte blocks, as many as the partition holds, littlefs 2.1 on disk. A
board whose table lists no "vfs" (the two P4s) gets MicroPython's own: the
flash from the end of the last partition to the end of the chip (ports/esp32
main.c), the chip's size being the one its bootloader's header names. The
image holds the used blocks only: it is made at the fewest blocks that fit,
so every block it allocates is in that prefix, and then grown to the
partition's count (lfs_fs_grow), which rewrites only the superblock.

littlefs-python (pyproject's dev extra) writes it; CI's firmware build
installs it beside zopfli. tests/test_store_image.py mounts the result in the
desktop MicroPython and reads the add-on back.

THE CHECK (`--check`) needs no board image: each board's store as its
sources lay it (`board_store`) must hold the add-on of the bundle built
(firmware/web_runner/dist, packed as gen_web_blob packs it), and a headless
board's, the only store it has, the carts its first boot writes beside it
(`first_boot`) with the room a seed leaves free (device/zero_host.py's
SEED_RESERVE: the system folder's and a kid's carts'). It fails naming the
board and the blocks. The pack sits in the store, so a bundle that grows past
a board's store is caught where it is built, before any image is
(tools/preflight.sh runs it after the browser console builds).
"""

import argparse
import ast
import glob
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

BLOCK = 4096                    # moy_kvfs.c's block size, and the flash's sector
READ = PROG = LOOKAHEAD = 32    # moy_kvfs.c's KV_READ, KV_PROG, KV_LOOKAHEAD
CACHE = 128                     # its KV_CACHE
CYCLES = 100
TABLE_AT = 0x8000               # CONFIG_PARTITION_TABLE_OFFSET on every board
STORE_LABEL = "vfs"
CARTS = "/moy/carts"            # the internal store's carts folder on every board
INSTALL = "_install"
FLASH_SIZES = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16, 5: 32, 6: 64, 7: 128}   # header nibble -> MB


class ImageError(Exception):
    pass


def partitions(merged, offset):
    """[(label, type, subtype, offset, size)] of the table in `merged` (the
    bytes written at flash `offset`)."""
    at = TABLE_AT - offset
    out = []
    for i in range(at, at + 0xC00, 32):
        magic = struct.unpack_from("<H", merged, i)[0]
        if magic != 0x50AA:
            break
        kind, sub, off, size = struct.unpack_from("<BBII", merged, i + 2)
        label = merged[i + 12:i + 28].split(b"\0", 1)[0].decode()
        out.append((label, kind, sub, off, size))
    if not out:
        raise ImageError("no partition table at 0x%x" % TABLE_AT)
    return out


def flash_bytes(merged):
    """The chip size the bootloader's header names (byte 3's high nibble)."""
    if merged[0] != 0xE9:
        raise ImageError("the image does not start with a bootloader (0x%02x)" % merged[0])
    mb = FLASH_SIZES.get(merged[3] >> 4)
    if mb is None:
        raise ImageError("the header names no flash size (0x%02x)" % merged[3])
    return mb << 20


def store_part(merged, offset):
    """(offset, size) of the internal store: the "vfs" partition, else the
    tail of the chip after the last partition."""
    return _store_of(partitions(merged, offset), lambda: flash_bytes(merged))


def _board_file(board_dir, name):
    for path in sorted(glob.glob(os.path.join(board_dir, "boards", "*", name))):
        return path
    raise ImageError("%s has no boards/*/%s" % (board_dir, name))


def board_store(board_dir):
    """store_part of the image a board's build writes, from its sources: the
    partition CSV its sdkconfig.board names and the chip size it names (the
    esp32 port's 4 MB where it names none)."""
    with open(_board_file(board_dir, "sdkconfig.board")) as f:
        cfg = f.read()
    name = re.search(r'^CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="([^"]+)"', cfg, re.M)
    if name is None:
        raise ImageError("%s's sdkconfig.board names no partition table" % board_dir)
    mb = re.search(r"^CONFIG_ESPTOOLPY_FLASHSIZE_(\d+)MB=y$", cfg, re.M)
    parts = []
    with open(_board_file(board_dir, os.path.basename(name.group(1)))) as f:
        for line in f:
            row = [c.strip() for c in line.split("#", 1)[0].split(",")]
            if len(row) >= 5 and row[0]:
                parts.append((row[0], row[1], row[2], int(row[3], 0), int(row[4], 0)))
    return _store_of(parts, lambda: (int(mb.group(1)) if mb else 4) << 20)


def _store_of(parts, chip_bytes):
    for label, _kind, _sub, off, size in parts:
        if label == STORE_LABEL:
            return off, size
    end = max(off + size for _l, _k, _s, off, size in parts)
    chip = chip_bytes()
    if chip <= end:
        raise ImageError("no room for a store after 0x%x on a %d MB chip" % (end, chip >> 20))
    return end, chip - end


def _fs(blocks):
    from littlefs import LittleFS
    return LittleFS(block_size=BLOCK, block_count=blocks, read_size=READ, prog_size=PROG,
                    lookahead_size=LOOKAHEAD, cache_size=CACHE, block_cycles=CYCLES)


def store_image(files, blocks):
    """The used blocks of a LittleFS of `blocks` blocks holding `files`
    ({absolute path: bytes})."""
    from littlefs import LittleFSError
    need = sum(-(-len(b) // BLOCK) for b in files.values())
    n = need + 4
    while True:
        if n > blocks:
            raise ImageError("%d B of files do not fit a store of %d blocks"
                             % (sum(map(len, files.values())), blocks))
        fs = _fs(n)
        try:
            for path, data in sorted(files.items()):
                fs.makedirs(path.rsplit("/", 1)[0], exist_ok=True)
                with fs.open(path, "wb") as f:
                    f.write(data)
            break
        except LittleFSError:
            n += max(4, n // 32)
    fs.fs_grow(blocks)
    fs.unmount()
    return bytes(fs.context.buffer[:n * BLOCK])


def addon_files(pack):
    """{path: bytes} of the add-on cart for the pack bytes `pack`, in CARTS."""
    import web_pack
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, web_pack.PACK_FILE)
        with open(path, "wb") as f:
            f.write(pack)
        files = web_pack._cart_files(path)
        folder = web_pack.cart_id(web_pack.digest_of(pack)) + ".moy"
    return {"%s/%s/%s" % (CARTS, folder, name): data for name, data in files.items()}


def install_image(merged, offset, pack):
    """The install: `merged` (written at `offset`), 0xFF to the store, and the
    store holding the add-on for `pack`. Raises ImageError, or web_pack's
    PageError for a pack that is not one."""
    at, size = store_part(merged, offset)
    if at - offset < len(merged):
        raise ImageError("the merged image runs into the store at 0x%x" % at)
    store = store_image(addon_files(pack), size // BLOCK)
    return merged + b"\xff" * (at - offset - len(merged)) + store


def first_boot(board_dir):
    """{path: bytes} of the carts a new store of the board's gets beside the
    add-on: the seed its image carries (`[roster] image`, every device seed
    cart where that is "all") and the official carts its cable flash adds
    (`[roster] install`), as the seed writes them."""
    import board_config
    import gen_device_carts
    import web_pack
    ids = board_config.roster_only(board_dir) or tuple(gen_device_carts.roster("device"))
    out = {}
    for folder in [c + ".moy" for c in ids + board_config.roster_install(board_dir)]:
        for rel, data in web_pack.seed_files(os.path.join(ROOT, "system_carts", folder)).items():
            out["%s/%s/%s" % (CARTS, folder, rel)] = data
    return out


def seed_reserve():
    """device/zero_host.py's SEED_RESERVE: the room a seed leaves free, read
    from its source."""
    with open(os.path.join(ROOT, "device", "zero_host.py")) as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "SEED_RESERVE" for t in node.targets):
            return eval(compile(ast.Expression(node.value), "zero_host", "eval"), {"__builtins__": {}})
    raise ImageError("device/zero_host.py names no SEED_RESERVE")


def _used(files, blocks):
    """The blocks `files` take in a store of `blocks` blocks, None where they
    do not fit."""
    from littlefs import LittleFSError
    fs = _fs(blocks)
    try:
        for path, data in sorted(files.items()):
            fs.makedirs(path.rsplit("/", 1)[0], exist_ok=True)
            with fs.open(path, "wb") as f:
                f.write(data)
    except LittleFSError:
        return None
    used = fs.used_block_count
    fs.unmount()
    return used


def room(board_dir, pack):
    """(the store's blocks, the blocks the add-on for `pack` takes in it, the
    blocks it and the first boot's carts take, None where they do not fit) of
    a board's store as its sources lay it. Raises ImageError where the
    add-on alone does not fit, as install_image does."""
    blocks = board_store(board_dir)[1] // BLOCK
    addon = addon_files(pack)
    alone = _used(addon, blocks)
    if alone is None:
        raise ImageError("%d B of files do not fit a store of %d blocks"
                         % (sum(map(len, addon.values())), blocks))
    return blocks, alone, _used(dict(addon, **first_boot(board_dir)), blocks)


def board_dirs():
    """Every board folder whose build writes an image with a store: a
    board.toml with a `[flash] image` and a partition table."""
    import board_config
    out = []
    for name in sorted(os.listdir(os.path.join(ROOT, "firmware"))):
        d = os.path.join(ROOT, "firmware", name)
        if (os.path.exists(os.path.join(d, "board.toml"))
                and board_config.load(d).get("flash", {}).get("image")
                and glob.glob(os.path.join(d, "boards", "*", "sdkconfig.board"))):
            out.append(d)
    return out


def check(pack, out=sys.stdout):
    """Each board's room for `pack` (bytes), a line each, and the boards
    that fail: every board's store must hold the add-on (the website's
    install), and a headless board's, its only store, the carts of its first
    boot beside it and the seed's reserve free. A console board seeds its
    carts on its card where one is in, so its line only says what a store
    with no card leaves."""
    import board_config
    reserve = -(-seed_reserve() // BLOCK)
    bad = []
    for d in board_dirs():
        name = os.path.basename(d)
        headless = board_config.load(d)["board"].get("tier") == "headless"
        try:
            blocks, addon, both = room(d, pack)
        except ImageError as exc:
            out.write("!! %-28s %s\n" % (name, exc))
            bad.append(name)
            continue
        line = "store %4d blocks, the add-on %4d (%2d%% left)" % (
            blocks, addon, 100 * (blocks - addon) // blocks)
        if both is None:
            short = True
            line += "; its first boot's carts do not fit beside it"
        else:
            short = blocks - both < reserve
            line += "; its first boot's carts %3d more, %4d free" % (both - addon, blocks - both)
        if headless:
            line += short and ", under the seed's reserve of %d" % reserve or ""
        else:
            line += " (with no card)"
        failed = headless and short
        out.write("%s %-28s %s\n" % ("!!" if failed else "  ", name, line))
        if failed:
            bad.append(name)
    return bad


def install_name(image):
    """`moybyte_tdeck.bin` -> `moybyte_tdeck_install.bin`."""
    stem, ext = os.path.splitext(image)
    return stem + INSTALL + ext


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("board_dir", nargs="?")
    ap.add_argument("--image", help="the merged image (default: board.toml's [flash] image)")
    ap.add_argument("--out", help="where to write it (default: beside the merged image)")
    ap.add_argument("--check", action="store_true",
                    help="every board's store against the bundle built (no image needed)")
    ap.add_argument("--pack", help="with --check: this pack instead of the bundle built")
    a = ap.parse_args()
    import board_config
    import web_pack
    if a.check:
        return main_check(a.pack)
    if a.board_dir is None:
        ap.error("name a board_dir, or --check")
    flash = board_config.load(a.board_dir)["flash"]
    image = a.image or os.path.join(ROOT, flash["image"])
    offset = int(str(flash.get("offset", "0x0")), 0)
    pack, _digest = web_pack.page_beside(image, board_config.load(a.board_dir)["board"]["ota"])
    with open(image, "rb") as f:
        merged = f.read()
    with open(pack, "rb") as f:
        body = f.read()
    try:
        out = install_image(merged, offset, body)
    except (ImageError, web_pack.PageError) as exc:
        print("!! %s: %s" % (a.board_dir, exc), file=sys.stderr)
        return 1
    dest = a.out or install_name(image)
    with open(dest + ".part", "wb") as f:
        f.write(out)
    os.replace(dest + ".part", dest)
    at, size = store_part(merged, offset)
    print("OK -> %s (%d B: the image, then the store at 0x%x of %d KB with the "
          "browser console add-on)" % (dest, len(out), at, size >> 10))
    return 0


def main_check(path):
    """--check: 0 when every board's store has the room `check` asks; 1
    naming the boards whose store does not."""
    import gen_web_blob
    if path:
        with open(path, "rb") as f:
            pack = f.read()
    else:
        assets, missing = gen_web_blob.collect(gen_web_blob.DEFAULT_DIST)
        if missing:
            print("!! no browser console in %s (%s): build it first, firmware/web_runner/build.sh"
                  % (gen_web_blob.DEFAULT_DIST, ", ".join(missing)), file=sys.stderr)
            return 1
        pack = gen_web_blob.pack(assets)[0]
    print("the browser console add-on: a %d B pack, %d blocks" % (len(pack), -(-len(pack) // BLOCK)))
    bad = check(pack)
    if bad:
        print("!! the browser console add-on outgrows the store of: %s (a headless board's "
              "holds its first boot's carts and the seed's reserve beside it)" % ", ".join(bad))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
