"""A card the console cannot read, and the one question it asks about it.

A card that answers but holds no volume the store reads -- no filesystem, an
unknown one, or a partition table FatFS does not read (GPT: owner,
2026-11-26, the question is the answer for such a card) -- is left as it
is, and the console runs on its internal store. Once the desktop
is up the console ASKS (owner, 2026-11-26), on every board with a slot:

    This card can't be read
    Format it for Moybyte? Everything on it will be erased.
    A 32 GB card. It seems to hold data.

with Format and Not now, by pad or touch (`ws.confirm`, the console's one
question, runtime/shell/confirm_ui.py). Nothing formats a card but an
explicit Format: it writes a FAT volume over the whole card (FAT32 with a
partition table on any card past FAT16's reach) and restarts the console,
whose next boot mounts the card as the store. Not now leaves the card
untouched; the question comes again the next time the console finds the
card, which on these slots (none has a card-detect line) is the next boot
with it in.

Where the card is found unreadable is the boards' mount (device/card_store.py,
device/moybyte_sd.py), which call `noticed(exc, card)` with the mount's
error and the card's sectors (`card`: `read(start, buf, count)`,
`write(start, buf, count)` and `sector_count()`, the board's `moy_sd`).

  OFFER        None, or {"sectors": n, "data": bool} while the question waits
  noticed(exc, card) -> OFFER     after a failed mount
  offer(ws) -> bool               put the question up, where one waits
  format(card)                    the volume written; raises OSError
"""

SECTOR = 512
ENODEV = 19                     # FatFS's FR_NO_FILESYSTEM, as the store raises it

OFFER = None
_CARD = [None]
_ASKED = [False]                # this boot's question was put: a retried mount asks nothing


def noticed(exc, card):
    """After the card's mount failed with `exc`: the question to ask, where
    the card answered and holds no volume this console reads (ENODEV);
    None for every other failure (no card, a dead bus)."""
    global OFFER
    code = exc.args[0] if getattr(exc, "args", None) else None
    if code != ENODEV or card is None or _ASKED[0]:
        return None
    try:
        n = card.sector_count()
        if not n:
            return None
        OFFER = {"sectors": n, "data": holds_data(card)}
        _CARD[0] = card
    except Exception:  # noqa: BLE001 -- a card that will not read is no question
        OFFER = None
    return OFFER


def holds_data(card):
    """Whether the card's first sectors look written: a partition table or
    boot sector's signature, a GPT header, an ext superblock, or any byte
    but zero."""
    buf = bytearray(3 * SECTOR)
    card.read(0, buf, 3)
    if buf[510] == 0x55 and buf[511] == 0xAA:
        return True
    if bytes(buf[SECTOR:SECTOR + 8]) == b"EFI PART":
        return True
    if buf[1080] == 0x53 and buf[1081] == 0xEF:
        return True
    return any(buf)


def size_words(sectors):
    b = sectors * SECTOR
    if b >= 1000 ** 3:
        return "%d GB" % ((b + 500 * 1000 ** 2) // 1000 ** 3)
    return "%d MB" % max(1, (b + 500 * 1000) // 1000 ** 2)


def words(offer):
    """The question's title and line."""
    line = "Format it for Moybyte? Everything on it will be erased. A %s card." % \
        size_words(offer["sectors"])
    if offer["data"]:
        line += " It seems to hold data."
    return "This card can't be read", line


class _Whole:
    """The whole card as VfsFat.mkfs's block device."""

    def __init__(self, card, n):
        self.card, self.n = card, n

    def readblocks(self, block, buf):
        self.card.read(block, buf, len(buf) // SECTOR)

    def writeblocks(self, block, buf):
        self.card.write(block, buf, len(buf) // SECTOR)

    def ioctl(self, op, arg):
        if op == 4:
            return self.n
        if op == 5:
            return SECTOR
        return 0


def format(card):  # noqa: A001 -- the verb's name
    """A FAT volume over the whole of `card`. Raises OSError."""
    try:
        import vfs
    except ImportError:
        import os as vfs
    vfs.VfsFat.mkfs(_Whole(card, card.sector_count()))


def offer(ws):
    """Put the question up where a card waits for one: True when asked."""
    global OFFER
    q, confirm = OFFER, getattr(ws, "confirm", None)
    if q is None or confirm is None:
        return False
    title, line = words(q)
    _ASKED[0] = True

    def not_now():
        global OFFER
        OFFER = None

    def yes():
        global OFFER
        OFFER = None
        card, _CARD[0] = _CARD[0], None
        try:
            format(card)
        except Exception as exc:  # noqa: BLE001 -- said, and the card is the store's no more than before
            ws.notices.notice("The card was not formatted", str(exc), "warn")
            return
        ws.notices.notice("The card is formatted", "Restarting to use it", "ok")
        hook = getattr(ws, "reboot_hook", None)
        if hook is not None:
            hook()

    return bool(confirm.ask_close(title, line, yes, "format", no=not_now))
