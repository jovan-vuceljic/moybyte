#!/usr/bin/env python3
"""The USB-Serial/JTAG console hands its bytes to Improv's frame parser
before the REPL sees them.

    python3 tools/patch_usj_improv.py <micropython checkout>

Improv Wi-Fi's serial frames (native/moy_kernel/moy_improv.h) share the
console with the REPL, and an RPC frame's type byte is 0x03, which the
port's receive path reads as Ctrl-C: a frame left to it would stop the
store host. So every read of the RX FIFO goes through `moy_improv_usj`
(native/moy_kernel/modmoy_improv.c), which keeps a frame's bytes and gives
the rest back in place, and the poll the REPL's read loop runs also reads
when the parser holds bytes, so a header held for its next byte is given
back once it goes stale. `rx_buf` grows by the bytes a read may give back.

Everything the patch adds is under `#if MOY_IMPROV`, which a board's
mpconfigboard.h defines (the Zeros); a tree built without it compiles the
stock body.

Applied by `moybyte_patch_usj_improv` in tools/esp32_build_lib.sh, to
`ports/esp32/usb_serial_jtag.c`. All-or-nothing: every hunk must match
exactly once or nothing is written and the exit is non-zero. A file already
carrying the marker is left as it is.
"""

from __future__ import annotations

import os
import sys

MARKER = "Moybyte: Improv's frames off the console"
FILE = "ports/esp32/usb_serial_jtag.c"

HUNKS = (
    ("#include \"usb_serial_jtag.h\"\n",
     "#include \"usb_serial_jtag.h\"\n"
     "\n"
     "// %s (native/moy_kernel/moy_improv.h,\n"
     "// tools/patch_usj_improv.py).\n"
     "#if MOY_IMPROV\n"
     "size_t moy_improv_usj(uint8_t *buf, size_t n, size_t cap);\n"
     "int moy_improv_held(void);\n"
     "#define MOY_IMPROV_SLACK (8)\n"
     "#else\n"
     "#define MOY_IMPROV_SLACK (0)\n"
     "#endif\n" % MARKER),
    ("static uint8_t rx_buf[USB_SERIAL_JTAG_PACKET_SZ_BYTES];\n",
     "static uint8_t rx_buf[USB_SERIAL_JTAG_PACKET_SZ_BYTES + MOY_IMPROV_SLACK];\n"),
    ("    size_t len = usb_serial_jtag_ll_read_rxfifo(rx_buf, req_len);\n",
     "    size_t len = usb_serial_jtag_ll_read_rxfifo(rx_buf, req_len);\n"
     "    #if MOY_IMPROV\n"
     "    len = moy_improv_usj(rx_buf, len, sizeof(rx_buf));\n"
     "    #endif\n"),
    ("    if (usb_serial_jtag_ll_rxfifo_data_available() && ringbuf_free(&stdin_ringbuf)) {\n",
     "    if ((usb_serial_jtag_ll_rxfifo_data_available() && ringbuf_free(&stdin_ringbuf))\n"
     "        #if MOY_IMPROV\n"
     "        || moy_improv_held()\n"
     "        #endif\n"
     "        ) {\n"),
)


def patch_text(text):
    """`text` with every hunk applied, or SystemExit naming the first that
    does not match exactly once."""
    for stock, patched in HUNKS:
        n = text.count(stock)
        if n != 1:
            sys.exit("!! USB-Serial/JTAG Improv patch did not apply -- %s matches "
                     "%r %d times (the stock file changed shape); nothing written"
                     % (FILE, stock.strip(), n))
        text = text.replace(stock, patched)
    return text


def apply(mpy_dir):
    """Patch the checkout under `mpy_dir`; returns "patched" or "already"."""
    path = os.path.join(mpy_dir, FILE)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if MARKER in text:
        return "already"
    text = patch_text(text)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return "patched"


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mpy_dir", help="the MicroPython checkout to patch "
                                    "(its ports/esp32 is what changes)")
    a = ap.parse_args(argv)
    if apply(a.mpy_dir) == "patched":
        print("== patched %s: Improv's frames off the console" % FILE)


if __name__ == "__main__":
    main()
