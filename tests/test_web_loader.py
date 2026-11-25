"""The loader (docs/web_console_online_2026-11.md §3, §4, §11 phase 1): the
page a board whose console is online serves at its root, which boots the
console from a pack it checks against the digest the image names.

- firmware/web_runner/loader_test.mjs drives the loader's script in node:
  a wrong digest, a tampered head and a poisoned cache entry refused, the
  source order, and eviction.
- The loader's gzipped size stays under its budget.
- The digests gen_web_blob names are the pack's, and the loader it carries
  is loader.html with the build's mirrors.
- serve.py serves this tree's pack by its digest, with CORS.
- tools/pack_store.py builds the store from a release's add-on carts, and
  its deploy check passes against a local serve.py serving this tree's pack.
- Under MOYBYTE_WEB_E2E, Chrome boots the console through the loader from
  serve.py's loader twin, then again from its cache.
"""

import contextlib
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER = os.path.join(ROOT, "firmware", "web_runner")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_web_blob  # noqa: E402
import pack_store  # noqa: E402
import web_pack  # noqa: E402

DIST = os.path.join(RUNNER, "dist")


def _have_dist():
    return not gen_web_blob.collect(DIST)[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_loader_in_node():
    p = subprocess.run(["node", "loader_test.mjs"], cwd=RUNNER,
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, "the loader test failed:\n%s\n%s" % (p.stdout, p.stderr)


def test_the_loader_stays_under_its_budget():
    """§3: a few KB in every image, held to 4 KiB gzipped with the longest
    mirror list a build names (a worktree's: its serve.py, then the site)."""
    gz = gen_web_blob.loader_gz(["http://192.168.100.200:%d/console/" % gen_web_blob.DEV_PORT,
                                 gen_web_blob.SITE_MIRROR])
    assert len(gz) <= gen_web_blob.LOADER_BUDGET, \
        "the loader is %d B gzipped, over its %d B budget" % (len(gz), gen_web_blob.LOADER_BUDGET)


def _c_bytes(text, name):
    m = re.search(r"const unsigned char %s\[\d*\] = \{([^}]*)\};" % name, text)
    return bytes(int(x, 16) for x in re.findall(r"0x([0-9a-f]{2})", m.group(1)))


def _fake_dist(d):
    os.makedirs(d)
    for i, name in enumerate(gen_web_blob.asset_names()):
        raw = ("%s %d\n" % (name, i)).encode() * (i + 3)
        with open(os.path.join(d, name), "wb") as f:
            f.write(raw)
        with open(os.path.join(d, name + ".gz"), "wb") as f:
            f.write(gzip.compress(raw, mtime=0))


def test_the_digests_the_image_names_are_the_pack_s(tmp_path):
    """The image names the body's sha256 (the pack's identity) and the whole
    file's (what the loader checks), both of the pack the same run wrote."""
    dist = str(tmp_path / "dist")
    _fake_dist(dist)
    out, pack = str(tmp_path / "blob.gen.c"), str(tmp_path / "moybyte_web.pack")
    mirrors = ["http://10.0.0.2:8321/console/", gen_web_blob.SITE_MIRROR]
    argv = ["--dist", dist, "--out", out, "--pack", pack, "--online", "--quiet"]
    for m in mirrors:
        argv += ["--mirror", m]
    assert gen_web_blob.main(argv) == 0
    text = open(out).read()
    data = open(pack, "rb").read()
    assert _c_bytes(text, "moy_web_want") == hashlib.sha256(data[4096:]).digest()
    assert _c_bytes(text, "moy_web_want") == data[16:48]      # the head's digest
    assert _c_bytes(text, "moy_web_pack_sha") == hashlib.sha256(data).digest()
    assert web_pack.digest_of(data) == _c_bytes(text, "moy_web_want").hex()
    assert "moy_web_named = 1u" in text and "moy_web_online = 1u" in text
    loader = _c_bytes(text, "moy_web_loader")
    assert "moy_web_loader_len = %du;" % len(loader) in text
    page = gzip.decompress(loader).decode()
    assert page == gen_web_blob.loader_page(mirrors)
    assert json.dumps(mirrors) in page and "@MIRRORS@" not in page


def test_an_image_with_no_bundle_names_no_pack_and_still_carries_the_loader(tmp_path):
    out = str(tmp_path / "blob.gen.c")
    env = dict(os.environ, MOYBYTE_REQUIRE_WEB_BUNDLE="0")
    env.pop("CI", None)
    p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "gen_web_blob.py"),
                        "--dist", str(tmp_path / "none"), "--out", out, "--quiet",
                        "--mirror", gen_web_blob.SITE_MIRROR],
                       env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    text = open(out).read()
    assert "moy_web_named = 0u" in text and "moy_web_online = 0u" in text
    assert _c_bytes(text, "moy_web_pack_sha") == bytes(32)
    assert gzip.decompress(_c_bytes(text, "moy_web_loader")).startswith(b"<!doctype html>")


def test_a_ci_build_names_the_site_alone_and_a_local_one_its_serve_py_first(monkeypatch):
    monkeypatch.delenv("MOYBYTE_WEB_MIRRORS", raising=False)
    monkeypatch.setenv("CI", "1")
    assert gen_web_blob.default_mirrors() == [gen_web_blob.SITE_MIRROR]
    monkeypatch.delenv("CI")
    monkeypatch.setattr(gen_web_blob, "lan_address", lambda: "192.168.1.7")
    assert gen_web_blob.default_mirrors() == [
        "http://192.168.1.7:%d/console/" % gen_web_blob.DEV_PORT, gen_web_blob.SITE_MIRROR]
    monkeypatch.setenv("MOYBYTE_WEB_MIRRORS", "http://a/console/ http://b/console/")
    assert gen_web_blob.default_mirrors() == ["http://a/console/", "http://b/console/"]


def _published(folder, items, board="c3_zero"):
    """A release folder as tools/web_pack.py publishes one: the add-on cart
    of the pack of `items` and the board's index naming it."""
    os.makedirs(folder, exist_ok=True)
    data, digest = gen_web_blob.pack_bytes(items)
    pack = os.path.join(folder, "build", web_pack.PACK_FILE)
    os.makedirs(os.path.dirname(pack))
    with open(pack, "wb") as f:
        f.write(data)
    shutil.copy(web_pack.LICENCE_SRC, os.path.join(folder, web_pack.LICENCE_NAME))
    cart = web_pack.publish_cart((pack, digest.hex()), folder)
    entry = web_pack.index_entry(digest.hex(), 7, cart, folder)
    with open(os.path.join(folder, "carts-%s.json" % board), "wb") as f:
        f.write(web_pack.index_doc(board, entry))
    return data, digest.hex(), os.path.join(folder, cart[0])


def test_the_store_holds_every_stable_pack_and_the_recent_dev_ones(tmp_path):
    stable_data, stable, _ = _published(str(tmp_path / "latest"), [("index.html", b"s")])
    dev_data, dev, _ = _published(str(tmp_path / "beta"), [("index.html", b"d")])
    _old_data, old, old_cart = _published(str(tmp_path / "beta_old"), [("index.html", b"o")])
    long_ago = time.time() - 40 * 86400
    os.utime(old_cart, (long_ago, long_ago))
    out = str(tmp_path / "store")
    got = pack_store.build(out, stable=[str(tmp_path / "latest")],
                           dev=[str(tmp_path / "beta"), str(tmp_path / "beta_old")])
    assert got == sorted([stable, dev]) and old not in got
    assert open(os.path.join(out, "console", stable + ".pack"), "rb").read() == stable_data
    assert open(os.path.join(out, "console", dev + ".pack"), "rb").read() == dev_data


def test_the_store_holds_the_pack_of_a_cart_no_index_names(tmp_path):
    """An online console's index names no add-on (the C3 Zero's), so the
    store reads a release's add-on carts by their names: its pack is served,
    checked against the digest its name carries."""
    data, digest, _cart = _published(str(tmp_path / "beta"), [("index.html", b"c")])
    os.remove(os.path.join(str(tmp_path / "beta"), "carts-c3_zero.json"))
    out = str(tmp_path / "store")
    assert pack_store.build(out, dev=[str(tmp_path / "beta")]) == [digest]
    assert open(os.path.join(out, "console", digest + ".pack"), "rb").read() == data
    wrong = os.path.join(str(tmp_path / "beta"), web_pack.CART_NAME % ("0" * 64))
    os.rename(_cart, wrong)
    with pytest.raises(pack_store.StoreError):
        pack_store.build(out, dev=[str(tmp_path / "beta")])


def test_the_store_refuses_a_cart_its_index_does_not_name(tmp_path):
    _data, _digest, cart = _published(str(tmp_path / "latest"), [("index.html", b"s")])
    with open(cart, "ab") as f:
        f.write(b"x")
    with pytest.raises(pack_store.StoreError):
        pack_store.build(str(tmp_path / "store"), stable=[str(tmp_path / "latest")])


@contextlib.contextmanager
def _serve(*extra):
    """firmware/web_runner/serve.py over this tree's dist/, up and answering."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from net_ports import free_port
    port = free_port()
    server = subprocess.Popen([sys.executable, "serve.py", str(port), "dist"] + list(extra),
                              cwd=RUNNER, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % port
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/sync", timeout=1).read()
                break
            except urllib.error.HTTPError:
                break
            except OSError:
                if server.poll() is not None:
                    pytest.fail("serve.py died on startup")
                time.sleep(0.1)
        yield base
    finally:
        server.terminate()
        server.wait(timeout=10)


@pytest.mark.skipif(not _have_dist(), reason="web_runner dist/ not built")
def test_serve_py_serves_this_tree_s_pack_by_its_digest_with_cors():
    data, here = gen_web_blob.pack(gen_web_blob.collect(DIST)[0])
    with _serve() as base:
        with urllib.request.urlopen(base + "/console/%s.pack" % here.hex()) as r:
            assert r.headers["Access-Control-Allow-Origin"] == "*"
            assert "immutable" in r.headers["Cache-Control"]
            assert r.read() == data
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/console/%s.pack" % ("ab" * 32))
        assert e.value.code == 404


@pytest.mark.skipif(not _have_dist(), reason="web_runner dist/ not built")
def test_the_deploy_check_passes_against_serve_py_and_names_what_is_missing(tmp_path):
    """§11's deploy check, against a local serve.py: every digest an index
    names is served, whole, to a board's origin, with
    Access-Control-Allow-Origin."""
    data, here = gen_web_blob.pack(gen_web_blob.collect(DIST)[0])
    index = tmp_path / "carts-c3_zero.json"

    def entry(digest):
        return {"id": web_pack.cart_id(digest), "runtime": web_pack.CART_RUNTIME,
                "assets": [{"name": "x", "url": "x"}], "moybyte": {"fits": digest}}
    index.write_text(json.dumps({"version": 1, "carts": [entry(here.hex())]}))
    with _serve() as base:
        assert pack_store.check(base, [str(index)]) == []
        req = urllib.request.Request(base + "/console/%s.pack" % here.hex())
        with urllib.request.urlopen(req) as r:
            assert r.headers["Access-Control-Allow-Origin"] == "*"
            assert "immutable" in r.headers["Cache-Control"]
            assert r.read() == data
        index.write_text(json.dumps({"version": 1, "carts": [entry(here.hex()),
                                                             entry("ab" * 32)]}))
        problems = pack_store.check(base, [str(index)])
    assert len(problems) == 1 and "ab" * 32 in problems[0], problems


@pytest.mark.skipif(not os.environ.get("MOYBYTE_WEB_E2E"),
                    reason="MOYBYTE_WEB_E2E not set (spawns headless Chrome)")
def test_chrome_boots_the_console_through_the_loader(tmp_path):
    """serve.py's loader twin is a board whose console is online: Chrome
    boots the console from its mirror, checked, and a reload from the
    origin's cache."""
    import web_e2e
    web_e2e.require("sync")
    store = tmp_path / "store"
    for cart in ("moybyte.star_catcher.moy", "moybyte.sakura.moy"):
        shutil.copytree(os.path.join(ROOT, "system_carts", cart), store / cart)
    web_e2e.warm_host_library()
    with _serve("--carts", str(store), "--loader") as base:
        doc = json.loads(urllib.request.urlopen(base + "/sync").read())
        assert doc["local"] == 0 and len(doc["pack"]) == 64
        run = subprocess.run(["node", "browsershot.mjs", "scenarios/loader_boot.json",
                              str(tmp_path / "shots")],
                             cwd=RUNNER, env=dict(os.environ, MOY_BASE=base),
                             capture_output=True, text=True, timeout=300)
    out = run.stdout
    assert run.returncode == 0 and "boot -> live" in out, out[-3000:] + run.stderr[-500:]
    assert '\\"from\\":\\"/console/\\"' in out, out[-3000:]
    assert '\\"from\\":\\"cache\\"' in out, out[-3000:]
