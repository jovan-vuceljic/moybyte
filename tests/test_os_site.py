"""os.moybyte.com/console/ as tools/os_site.py builds it
(docs/web_console_online_2026-11.md §2's flow 2, §4, §5, §8): My consoles,
its service worker and the pack store, one folder of the Pages site.

The link's two ends are driven elsewhere: the loader's in node
(firmware/web_runner/loader_test.mjs), both across two origins in Chrome
(tests/test_web_link_e2e.py, a browser suite).
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_web_blob  # noqa: E402
import os_site  # noqa: E402
import pack_store  # noqa: E402
from test_web_loader import _published  # noqa: E402


def _pack(tmp_path, text):
    data, digest = gen_web_blob.pack_bytes([("index.html", text)])
    path = tmp_path / ("%s.pack" % digest.hex()[:8])
    path.write_bytes(data)
    return str(path), data, digest.hex()


def test_the_site_holds_my_consoles_and_the_packs_and_keeps_the_newest(tmp_path):
    _stable_data, stable, _ = _published(str(tmp_path / "latest"), [("index.html", b"s")])
    _old_data, old, old_cart = _published(str(tmp_path / "beta"), [("index.html", b"o")])
    old_pub = time.time() - 5 * 86400
    os.utime(old_cart, (old_pub, old_pub))
    path, data, local = _pack(tmp_path, b"a worktree's")
    out = tmp_path / "site"
    (out / "dev").mkdir(parents=True)                   # the rest of the Pages site
    (out / "index.html").write_text("the project site")
    held = os_site.build(str(out), stable=[str(tmp_path / "latest")],
                         dev=[str(tmp_path / "beta")], packs=[path])
    assert held == sorted([stable, old, local])
    folder = out / "console"
    assert (folder / (local + ".pack")).read_bytes() == data
    for name in os_site.FILES + tuple(os_site.ICONS) + ("sw.js", "packs.json"):
        assert (folder / name).is_file(), name
    assert json.loads((folder / "packs.json").read_text()) == {"newest": [stable, old, local]}
    assert (folder / "icon-512.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert (out / "index.html").read_text() == "the project site" and (out / "dev").is_dir()
    assert sorted(os.listdir(out)) == ["console", "dev", "index.html"]   # no header file


def test_the_service_worker_keeps_every_file_of_the_site_and_changes_with_it(tmp_path):
    path, _data, _d = _pack(tmp_path, b"p")
    os_site.build(str(tmp_path / "a"), packs=[path])
    folder = tmp_path / "a" / "console"
    sw = (folder / "sw.js").read_text()
    shell = json.loads(re.search(r"SHELL = (\[.*?\])", sw).group(1))
    assert shell == os_site.SHELL and "@" not in sw
    for name in shell:
        assert (folder / ("index.html" if name == "./" else name)).is_file(), name
    # Every file the page loads is one the worker keeps.
    page = (folder / "index.html").read_text()
    for ref in re.findall(r'(?:src|href)="([^"#:]+)"', page):
        assert ref in shell, ref
    path2, _data, _d = _pack(tmp_path, b"q")
    os_site.build(str(tmp_path / "b"), packs=[path2])
    version = re.compile(r'VERSION = "([0-9a-f]+)"')
    assert version.search(sw).group(1) != version.search(
        (tmp_path / "b" / "console" / "sw.js").read_text()).group(1)


def test_my_consoles_is_where_the_images_fetch_their_packs():
    """The mirror an image names is My consoles' own folder, so the pack it
    fetches is one the page's service worker can keep."""
    assert gen_web_blob.SITE_MIRROR == "https://os.moybyte.com/console/"
    assert '"scope": "./"' in open(os.path.join(os_site.SOURCE, "manifest.webmanifest")).read()


def test_the_page_never_asks_for_a_browsing_context_of_its_own():
    """The link's window keeps its opener only while no page of the site
    sends Cross-Origin-Opener-Policy; its policy rides a meta tag."""
    page = open(os.path.join(os_site.SOURCE, "index.html")).read()
    assert "cross-origin-opener-policy" not in page.lower()
    assert "default-src 'self'" in page


def test_the_site_never_evaluates_what_a_window_sends():
    """What a console's window posts is data: shown as text, never run."""
    for name in ("consoles.js", "packs.js", "sw.js"):
        src = open(os.path.join(os_site.SOURCE, name)).read()
        for bad in ("eval(", "innerHTML", "new Function", "insertAdjacentHTML", "document.write"):
            assert bad not in src, (name, bad)


def test_a_pack_that_is_none_is_refused(tmp_path):
    bad = tmp_path / "x.pack"
    bad.write_bytes(b"not a pack")
    with pytest.raises(pack_store.StoreError):
        os_site.build(str(tmp_path / "s"), packs=[str(bad)])


def test_serve_answers_as_pages_does(tmp_path):
    from net_ports import free_port
    path, data, digest = _pack(tmp_path, b"p")
    os_site.build(str(tmp_path / "s"), packs=[path])
    port = free_port()
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "os_site.py"), "serve",
                          str(tmp_path / "s"), "--port", str(port)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % port
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/console/", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with urllib.request.urlopen(base + "/console/%s.pack" % digest) as r:
            assert r.headers["Access-Control-Allow-Origin"] == "*"
            assert r.read() == data
        with urllib.request.urlopen(base + "/console/") as r:
            assert b"My consoles" in r.read() and r.headers["Cache-Control"] == "max-age=600"
        with urllib.request.urlopen(base + "/console/sw.js") as r:
            assert r.headers["Content-Type"].startswith("text/javascript")
        assert pack_store.check(base, []) == ["the indexes name no browser console"]
    finally:
        p.terminate()
        p.wait(timeout=10)
