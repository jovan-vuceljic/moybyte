"""The site's player and its channel's release (#124): os.moybyte.com mirrors
each release's indexes and the official carts' files beside them
(tools/pack_store.py), the player bakes in the release's public keys
(tools/ota_sign.py keys-module) and lists the official carts of the index
site/build.py names for its channel (`own`) only when that index's signature
verifies under them -- never because of where it was read from.

The browser half runs in Chrome in tests/test_web_store_e2e.py."""

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from cart_store_fixtures import MemNet
from runtime import cart_index as ci, moy_carts, pkg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "site"))

import ota_sign  # noqa: E402
import pack_store  # noqa: E402
import web_pack  # noqa: E402
from test_official_carts import OwnInst, SEEDS, _drain, _page, _rows, _seeded  # noqa: E402
from test_ota_signing import TEST_KEYS  # noqa: E402
from test_pkg import _sign  # noqa: E402

TAG = "firmware-beta"
MIRROR = "http://mirror.invalid/console/releases/%s/" % TAG
OWN = MIRROR + "carts-p4.json"


def _seeds(tmp_path, *ids):
    d = tmp_path / "seeds"
    for cid in ids:
        shutil.copytree(SEEDS / (cid + ".moy"), d / (cid + ".moy"))
    return d


def _mirrored(tmp_path, ids=("moybyte.bullet_storm", "moybyte.coin_quest")):
    """A signed release of the official carts `ids` for the P4, as
    pack_store fetches one, and the site's console folder built from it:
    (the release folder, the mirror's folder, its files as routes)."""
    rel = tmp_path / "release"
    rel.mkdir()
    web_pack.publish_addon(_page(tmp_path), str(rel), "p4", 9, seeds=str(_seeds(tmp_path, *ids)))
    idx = rel / "carts-p4.json"
    idx.write_bytes(_sign(idx.read_bytes()))
    (rel / pack_store.TAG_FILE).write_text(TAG + "\n")
    out = tmp_path / "site"
    pack_store.build(str(out), dev=[str(rel)])
    mirror = out / "console" / "releases" / TAG
    return rel, mirror, {MIRROR + n: (mirror / n).read_bytes() for n in os.listdir(mirror)}


@pytest.fixture
def site_keys(monkeypatch):
    """A page: no kernel to verify with, the release keys baked in."""
    monkeypatch.setattr(ci, "_native", lambda: None)
    monkeypatch.setattr(ci, "INDEX_KEYS", TEST_KEYS)


# -- the mirror -------------------------------------------------------------------


def test_the_mirror_holds_each_release_s_official_carts_beside_its_indexes(tmp_path):
    rel, mirror, _routes = _mirrored(tmp_path)
    index = (rel / "carts-p4.json").read_bytes()
    named = web_pack.shelf_files(index)
    zips = [n for n in named if n.endswith(".zip")]
    assert len(zips) == 2 and web_pack.LICENCE_NAME in named
    assert any(n.endswith(".png") for n in named), "a cover beside its cart"
    for name in named:
        assert (mirror / name).read_bytes() == (rel / name).read_bytes(), name
    assert (mirror / "carts-p4.json").read_bytes() == index
    # an add-on's cart is the store's pack, never a mirrored zip
    addon = [n for n in os.listdir(rel) if n.startswith("moybyte_web-") and n.endswith(".zip")]
    assert addon and not set(addon) & set(os.listdir(mirror))
    assert sorted(os.listdir(mirror)) == sorted(set(named) | {"carts-p4.json"})


def test_the_mirror_keeps_only_what_the_indexes_name_as_they_name_it(tmp_path, capsys):
    """An earlier zip still on the release is not mirrored, and a file that
    is not the one its entry names is left out and said."""
    rel = tmp_path / "release"
    rel.mkdir()
    web_pack.publish_addon(_page(tmp_path), str(rel), "p4", 9,
                           seeds=str(_seeds(tmp_path, "moybyte.bullet_storm", "moybyte.coin_quest")))
    (rel / pack_store.TAG_FILE).write_text(TAG + "\n")
    (rel / "moybyte.bullet_storm-000000000000.zip").write_bytes(b"an earlier build")
    named = web_pack.shelf_files((rel / "carts-p4.json").read_bytes())
    quest, = [n for n in named if n.startswith("moybyte.coin_quest-") and n.endswith(".zip")]
    (rel / quest).write_bytes((rel / quest).read_bytes()[:-1] + b"!")
    out = tmp_path / "site"
    pack_store.build(str(out), dev=[str(rel)])
    held = os.listdir(out / "console" / "releases" / TAG)
    assert "moybyte.bullet_storm-000000000000.zip" not in held
    assert quest not in held
    assert "is not the file its index names" in capsys.readouterr().err
    assert set(named) - {quest} <= set(held)


def test_a_folder_that_names_no_tag_mirrors_nothing(tmp_path):
    rel = tmp_path / "release"
    rel.mkdir()
    web_pack.publish_addon(_page(tmp_path), str(rel), "p4", 9,
                           seeds=str(_seeds(tmp_path, "moybyte.bullet_storm")))
    pack_store.build(str(tmp_path / "site"), stable=[str(rel)])
    assert not (tmp_path / "site" / "console" / "releases").exists()


# -- the signature ----------------------------------------------------------------


def test_the_site_s_release_is_official_once_its_signature_verifies(tmp_path, site_keys):
    _rel, _mirror, routes = _mirrored(tmp_path)
    got = ci.fitting(ci.parse_index(routes[OWN], OWN, OWN), want=None)
    official = {c["id"] for c in got if ci.is_official(c)}
    assert official == {"moybyte.bullet_storm", "moybyte.coin_quest"}
    assert not [c for c in got if c["runtime"] == "web"], "the add-ons fit boards' pages"
    assert not ci.addon_unfit(ci.parse_index(routes[OWN], OWN, OWN)), \
        "a page that names none has no add-on to miss"


def test_a_tampered_index_lists_nothing(tmp_path, site_keys):
    _rel, _mirror, routes = _mirrored(tmp_path)
    bad = routes[OWN].replace(b'"name": "Bullet Storm"', b'"name": "Bullet Storn"')
    assert bad != routes[OWN]
    with pytest.raises(ci.InstallError) as e:
        ci.parse_index(bad, OWN, OWN)
    assert e.value.text == ci.BAD_SIGNATURE


def test_an_index_is_never_official_for_where_it_was_read(tmp_path, monkeypatch):
    """With no key to check it by, the release's own index at its own
    address lists no built-in; under a key it does not verify by, it is
    refused."""
    _rel, _mirror, routes = _mirrored(tmp_path)
    monkeypatch.setattr(ci, "_native", lambda: None)
    monkeypatch.setattr(ci, "INDEX_KEYS", None)
    assert not [c for c in ci.parse_index(routes[OWN], OWN, OWN) if ci.is_official(c)]
    monkeypatch.setattr(ci, "INDEX_KEYS", (("%x" % (2 ** 2047 + 1), 65537),))
    with pytest.raises(ci.InstallError):
        ci.parse_index(routes[OWN], OWN, OWN)


# -- listing and installing in the player -----------------------------------------


def test_the_player_installs_an_unseeded_official_cart_from_the_mirror(tmp_path, site_keys):
    _rel, _mirror, routes = _mirrored(tmp_path)
    root = str(tmp_path / "moybyte" / "carts")
    os.makedirs(root)
    net = MemNet(routes)
    inst = OwnInst(root, net, own=OWN)
    assert ci.load_indexes(root, inst.own())[-1] == OWN
    carts = ci.fitting(ci.parse_index(routes[OWN], OWN, OWN), want=None)
    c, = [c for c in carts if c["id"] == "moybyte.bullet_storm"]
    assert _rows(root, carts)[c["folder"]] == "get"
    job = ci.Install(c, ci.plan(c, ranges=False), net, root, inst.op)
    while job.step():
        pass
    assert job.path, job.error
    _drain(pkg.landed(inst, job.path, None))
    assert os.path.exists(os.path.join(root, c["folder"], "main.lua"))
    assert all(u.startswith(MIRROR) for u in net.opened), net.opened


def test_a_removed_official_cart_comes_back_from_the_mirror(tmp_path, site_keys):
    root, _seed, _shelf = _seeded(tmp_path)
    _rel, _mirror, routes = _mirrored(tmp_path)
    net = MemNet(routes)
    inst = OwnInst(root, net, own=OWN)
    quest = "moybyte.coin_quest.moy"
    _drain(pkg.removed(inst, quest))
    assert moy_carts.load_removed(root) == [quest]
    carts = ci.fitting(ci.parse_index(routes[OWN], OWN, OWN), want=None)
    assert _rows(root, carts)[quest] == "get"
    c, = [c for c in carts if c["folder"] == quest]
    job = ci.Install(c, ci.plan(c), net, root, inst.op)
    while job.step():
        pass
    assert job.path, job.error
    _drain(pkg.landed(inst, job.path, None))
    assert moy_carts.load_removed(root) == []
    assert _rows(root, carts)[quest] == "installed"


# -- what the site and the bundle carry -------------------------------------------


def test_the_bundle_s_keys_are_the_ones_every_board_trusts(tmp_path):
    from device import moy_ota
    path = tmp_path / "release_keys.py"
    assert ota_sign.main(["keys-module", str(path)]) == 0
    ns = {}
    exec(path.read_text(), ns)
    assert ns["KEYS"] == tuple(tuple(k) for k in moy_ota.OTA_PUBLIC_KEYS)
    assert ns["KEYS"], "a release keyless would make no index official"


def test_each_channel_s_player_names_its_release_on_the_site():
    import build as site_build
    assert site_build.RELEASE_MIRROR == ci.RELEASE_MIRROR
    assert site_build.RELEASE_INDEX == web_pack.INDEX_NAME % "p4"
    stable = site_build.player_shelves()
    dev = site_build.player_shelves("dev")
    assert stable == {"own": ci.RELEASE_MIRROR + "firmware-latest/carts-p4.json"}
    assert dev == {"own": ci.RELEASE_MIRROR + "firmware-beta/carts-p4.json"}
    for doc in (stable, dev):
        assert "indexes" not in doc, "the shelves stay the console's defaults"


def test_a_site_page_takes_its_release_from_indexes_json(tmp_path):
    from test_web_store import _web_boot
    wb = _web_boot()
    carts = tmp_path / "carts"
    carts.mkdir()
    was = dict(wb._S)
    try:
        wb._S["store_mode"] = "board"
        wb._S.pop("cart_own", None)
        wb.site_sources(str(carts), json.dumps({"own": OWN}))
        assert "cart_own" not in wb._S, "a board's page lists the board's release"
        wb._S["store_mode"] = "site"
        wb.site_sources(str(carts), json.dumps({"own": "carts-p4.json"}))
        assert "cart_own" not in wb._S, "an address, never a path"
        wb.site_sources(str(carts), json.dumps({"own": OWN}))
        assert wb._S["cart_own"] == OWN
        assert not (tmp_path / "system" / "sources").exists(), \
            "no shelves named: the console's defaults"
    finally:
        wb._S.clear()
        wb._S.update(was)
