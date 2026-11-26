#!/usr/bin/env python3
"""The browser console as a home-screen app: its web app manifest and Moy's
icons, which `firmware/web_runner/build.sh` writes into dist/ beside the page
(both builds: the site's and the pack a board serves, whose webhost names
them in its ASSETS table, native/moy_net/moy_webhost.c).

An iPhone's Safari has no element full screen; a page saved to its Home
Screen opens with no browser bars, which is the iPhone's full screen
(page_core.html's head carries iOS's tags beside the manifest). Android's
Chrome installs the same manifest. `start_url` and `scope` are the page's own
folder, so the app opens the origin it was saved from: os.moybyte.com, or a
board's own address. No service worker: iOS makes a standalone app of a plain
http page on the LAN without one.

    tools/web_app.py OUT_DIR
"""

import argparse
import base64
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The page's own colour (page_core.html's html,body background): the splash
# and the bars around the app are the page's.
BG = "#0b0f1a"
# {file: (size, scale)}: the 16-pixel mascot, `scale` pixels an art pixel,
# centred on a `size` square of BG -- two thirds of it, inside a maskable
# icon's safe zone. 180 is iOS's apple-touch-icon, 192 and 512 the manifest's.
ICONS = {"icon-180.png": (180, 7), "icon-192.png": (192, 8), "icon-512.png": (512, 21)}


def manifest():
    """The web app manifest, as a dict."""
    return {"name": "Moybyte", "short_name": "Moybyte", "start_url": "./", "scope": "./",
            "display": "fullscreen", "display_override": ["fullscreen", "standalone"],
            "orientation": "any", "background_color": BG, "theme_color": BG,
            "icons": [{"src": name, "sizes": "%dx%d" % (size, size), "type": "image/png",
                       "purpose": "any maskable"}
                      for name, (size, _s) in ICONS.items() if name != "icon-180.png"]}


def icons():
    """{file: PNG bytes}: the Moy mascot as the project site draws it."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    spec = importlib.util.spec_from_file_location("moy_site_build", os.path.join(ROOT, "site", "build.py"))
    site = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(site)
    pal = site.palette()
    return {name: base64.b64decode(site.moy_mark(pal, scale, size, BG).split(",", 1)[1])
            for name, (size, scale) in ICONS.items()}


def write(out):
    """Write the manifest and the icons into `out`."""
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "manifest.webmanifest"), "w", encoding="utf-8") as f:
        json.dump(manifest(), f, indent=1)
        f.write("\n")
    for name, png in icons().items():
        with open(os.path.join(out, name), "wb") as f:
            f.write(png)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write the browser console's web app manifest "
                                             "and Moy's icons into a folder.")
    ap.add_argument("out", help="the folder (build.sh passes dist/)")
    write(ap.parse_args(argv).out)


if __name__ == "__main__":
    main()
