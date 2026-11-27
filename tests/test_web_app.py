"""The browser console as a home-screen app (tools/web_app.py): its manifest,
Moy's icons, the page's iOS tags and the safe area, and the files reaching
both builds -- the site's dist and the pack a board serves."""
import os
import re
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_web_blob  # noqa: E402
import web_app  # noqa: E402

PAGE = os.path.join(ROOT, "firmware", "web_runner", "page_core.html")
FILES = ["manifest.webmanifest"] + list(web_app.ICONS)


def _page():
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


def _png(data):
    """(width, height, first pixel's RGBA) of an 8-bit RGBA PNG."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h, depth, kind = struct.unpack(">IIBB", data[16:26])
    assert (depth, kind) == (8, 6)
    idat = b"".join(data[i + 8:i + 8 + struct.unpack(">I", data[i:i + 4])[0]]
                    for i in [m.start() - 4 for m in re.finditer(b"IDAT", data)])
    raw = zlib.decompress(idat)
    return w, h, tuple(raw[1:5])


def test_the_manifest_opens_the_page_full_screen_where_it_was_saved():
    m = web_app.manifest()
    assert m["name"] == "Moybyte" and m["short_name"]
    assert m["start_url"] == "./" and m["scope"] == "./", "the origin it was saved from"
    assert m["display"] == "fullscreen" and m["display_override"] == ["fullscreen", "standalone"]
    assert m["orientation"] == "any"
    assert m["background_color"] == m["theme_color"] == web_app.BG
    assert {i["sizes"] for i in m["icons"]} == {"192x192", "512x512"}
    assert all(i["src"] in web_app.ICONS for i in m["icons"])


def test_the_icons_are_moy_on_the_page_s_colour():
    bg = tuple(int(web_app.BG[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
    for name, png in web_app.icons().items():
        size = web_app.ICONS[name][0]
        assert _png(png) == (size, size, bg), name
        assert 16 * web_app.ICONS[name][1] <= size * 3 // 4, "inside a maskable icon's safe zone"


def test_the_page_carries_the_app_s_tags_and_its_colour():
    page = _page()
    # the page's ground is the scheme's token, the app's colour its night value
    assert re.search(r"html,body\{[^}]*background:var\(--pg\)", page)
    assert web_app.BG == re.search(r":root\{--pg:(#[0-9a-f]{6})", page).group(1)
    assert '<link rel=manifest href="manifest.webmanifest">' in page
    assert '<link rel=apple-touch-icon href="icon-180.png">' in page
    assert "<meta name=apple-mobile-web-app-capable content=yes>" in page
    assert "<meta name=apple-mobile-web-app-status-bar-style content=black-translucent>" in page
    assert '<meta name=theme-color content="%s">' % web_app.BG in page
    vp = re.search(r'<meta name=viewport content="([^"]+)">', page).group(1).split(",")
    assert {"viewport-fit=cover", "maximum-scale=1", "user-scalable=no"} <= set(vp), vp
    for side in ("top", "right", "bottom", "left"):
        assert "env(safe-area-inset-%s,0px)" % side in page, side


def test_both_builds_carry_the_app_s_files():
    """The pack holds what the webhost's ASSETS table names, and build.sh
    gzips each of them beside its raw file for the boards."""
    names = gen_web_blob.asset_names()
    for name in FILES:
        assert name in names, name
    with open(os.path.join(ROOT, "firmware", "web_runner", "build.sh"), encoding="utf-8") as f:
        sh = f.read()
    assert 'tools/web_app.py" "${DIST_DIR}"' in sh
    gz = re.search(r"for f in (index.html[^;]+); do", sh).group(1).replace("\\\n", " ").split()
    assert gz == names, "build.sh gzips the ASSETS table's files, all of them"


def test_write_puts_the_files_in_a_folder(tmp_path):
    web_app.write(str(tmp_path))
    assert sorted(os.listdir(tmp_path)) == sorted(FILES)
