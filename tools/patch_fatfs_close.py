#!/usr/bin/env python3
"""A FAT file's close is final: a VfsFat file whose close the card refused is
closed all the same, and never touches the volume again.

    python3 tools/patch_fatfs_close.py <micropython checkout>

Stock VfsFat (extmod/vfs_fat_file.c) raises when f_close fails and keeps the
FIL open, and its finaliser (`__del__`, the stream's close) runs that close
again at the next collection. oofatfs is built FF_FS_LOCK 0, so meanwhile
nothing stops the program removing or rewriting the file: the store's writers
remove a `.new` or `.part` whose close failed (the dev channel's `recv`,
`pkg`'s index cache, an install's unpack). The finaliser's f_sync then
writes the dead file's entry (attribute, first cluster, size) into whatever
now sits at its old directory slot: another file's long name, which lists as
a garbage 8.3 entry and a UnicodeError, with a freed chain recorded in it.
tests/test_card_aborts.py makes that happen without this patch.

Closed for good, the failed close costs what a power cut there would: the
entry's last update and the space its chain holds.

Applied by `moybyte_patch_fatfs_close` in tools/esp32_build_lib.sh and by `make
unix-micropython`. All-or-nothing: every hunk must match exactly once or
nothing is written and the exit is non-zero, naming the hunk. A tree already
carrying the marker is left as it is.
"""

from __future__ import annotations

import os
import sys

MARKER = "Moybyte: a close is final"

HUNKS = [
    ("extmod/vfs_fat_file.c", "close",
     "        if (self->fp.obj.fs != NULL) {\n"
     "            FRESULT res = f_close(&self->fp);\n"
     "            if (res != FR_OK) {\n",
     "        // %s, refused or not: the finaliser never closes it\n"
     "        // again into a directory slot that has moved on\n"
     "        // (tools/patch_fatfs_close.py).\n"
     "        if (self->fp.obj.fs != NULL) {\n"
     "            FRESULT res = f_close(&self->fp);\n"
     "            self->fp.obj.fs = NULL;\n"
     "            if (res != FR_OK) {\n" % MARKER),
]


def apply(mpy_dir):
    """Patch the checkout under `mpy_dir`; returns "patched", "already", or
    raises SystemExit naming the hunk that did not match exactly once."""
    paths = sorted({f for f, _, _, _ in HUNKS})
    texts = {}
    for rel in paths:
        with open(os.path.join(mpy_dir, rel), encoding="utf-8") as fh:
            texts[rel] = fh.read()
    if all(MARKER in texts[rel] for rel in paths):
        return "already"
    for rel, name, old, new in HUNKS:
        n = texts[rel].count(old)
        if n != 1:
            sys.exit("!! FatFS close patch did not apply -- %s hunk %r matches %d "
                     "times (the stock lines changed shape); nothing written"
                     % (rel, name, n))
        texts[rel] = texts[rel].replace(old, new)
    for rel in paths:
        with open(os.path.join(mpy_dir, rel), "w", encoding="utf-8") as fh:
            fh.write(texts[rel])
    return "patched"


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mpy_dir", help="the MicroPython checkout to patch (its extmod/vfs_fat_file.c)")
    a = ap.parse_args(argv)
    if apply(a.mpy_dir) == "patched":
        print("== patched extmod/vfs_fat_file.c: a FAT file's close is final")


if __name__ == "__main__":
    main()
