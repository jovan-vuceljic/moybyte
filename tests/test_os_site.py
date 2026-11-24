"""os.moybyte.com as tools/os_site.py builds it (docs/web_console_online_2026-11.md
§2's flow 2, §4, §5, §8): My consoles, its service worker and the pack store.

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
    held = os_site.build(str(out), stable=[str(tmp_path / "latest")],
                         dev=[str(tmp_path / "beta")], packs=[path])
    assert held == sorted([stable, old, local])
    assert (out / "console" / (local + ".pack")).read_bytes() == data
    for name in os_site.FILES + tuple(os_site.ICONS) + ("sw.js", "packs.json"):
        assert (out / name).is_file(), name
    assert json.loads((out / "packs.json").read_text()) == {"newest": [stable, old, local]}
    assert (out / "icon-512.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_the_service_worker_keeps_every_file_of_the_site_and_changes_with_it(tmp_path):
    path, _data, _d = _pack(tmp_path, b"p")
    os_site.build(str(tmp_path / "a"), packs=[path])
    sw = (tmp_path / "a" / "sw.js").read_text()
    shell = json.loads(re.search(r"SHELL = (\[.*?\])", sw).group(1))
    assert shell == os_site.SHELL and "@" not in sw
    for name in shell:
        assert (tmp_path / "a" / ("index.html" if name == "./" else name)).is_file(), name
    # Every file the page loads is one the worker keeps.
    page = (tmp_path / "a" / "index.html").read_text()
    for ref in re.findall(r'(?:src|href)="([^"#:]+)"', page):
        assert ref in shell, ref
    path2, _data, _d = _pack(tmp_path, b"q")
    os_site.build(str(tmp_path / "b"), packs=[path2])
    version = re.compile(r'VERSION = "([0-9a-f]+)"')
    assert version.search(sw).group(1) != version.search(
        (tmp_path / "b" / "sw.js").read_text()).group(1)


def test_the_headers_serve_packs_to_any_origin_and_the_site_fresh(tmp_path):
    path, _data, digest = _pack(tmp_path, b"p")
    os_site.build(str(tmp_path / "s"), packs=[path])
    rules = os_site.read_headers(str(tmp_path / "s" / "_headers"))
    pack = dict(os_site.headers_for(rules, "/console/%s.pack" % digest))
    assert pack["Access-Control-Allow-Origin"] == "*" and "immutable" in pack["Cache-Control"]
    for name in ("/", "/sw.js", "/consoles.js", "/packs.json"):
        assert dict(os_site.headers_for(rules, name))["Cache-Control"] == "no-cache", name
    csp = dict(os_site.headers_for(rules, "/"))["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp
    # The link's window keeps its opener only if the site never asks for a
    # browsing context of its own.
    assert "cross-origin-opener-policy" not in (tmp_path / "s" / "_headers").read_text().lower()


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


def test_serve_answers_as_the_host_does(tmp_path):
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
                urllib.request.urlopen(base + "/", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with urllib.request.urlopen(base + "/console/%s.pack" % digest) as r:
            assert r.headers["Access-Control-Allow-Origin"] == "*"
            assert "immutable" in r.headers["Cache-Control"]
            assert r.read() == data
        with urllib.request.urlopen(base + "/") as r:
            assert b"My consoles" in r.read() and r.headers["Cache-Control"] == "no-cache"
            assert "frame-ancestors" in r.headers["Content-Security-Policy"]
        with urllib.request.urlopen(base + "/sw.js") as r:
            assert r.headers["Content-Type"].startswith("text/javascript")
    finally:
        p.terminate()
        p.wait(timeout=10)
