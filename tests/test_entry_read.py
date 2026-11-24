"""A console reads one cart's entry of an index as it streams
(cart_index.EntryRead), never the whole document: the entry it answers is
the one parse_index answers, wherever a read's pieces split the text, the
signature is checked over a digest of what it covers, and a release's
index read from its mirror (cart_index.index_mirror) is the release's."""

import hashlib
import io
import json
import sys

import pytest

from cart_store_fixtures import MemNet, Repo
from runtime import cart_index as ci
from test_ota_signing import TEST_KEYS
from test_pkg import BASE, _sign

URL = BASE + "/index.json"


class _Bits:
    """A response that hands over at most `k` bytes a read."""

    def __init__(self, data, k):
        self._b = io.BytesIO(data)
        self.k = k
        self.status = 200
        self.length = len(data)

    def readinto(self, buf):
        return self._b.readinto(memoryview(buf)[:self.k])

    def close(self):
        pass


class BitsNet(MemNet):
    def __init__(self, routes, k):
        MemNet.__init__(self, routes)
        self.k = k

    def open(self, url):
        self.opened.append(url)
        got = self.routes.get(url)
        if got is None:
            return MemNet.open(self, url)
        return _Bits(got, self.k)


@pytest.fixture
def keys(monkeypatch):
    from runtime import net_binding
    monkeypatch.setitem(sys.modules, "moy_net", net_binding)
    monkeypatch.setattr(ci, "INDEX_KEYS", TEST_KEYS)
    monkeypatch.setattr(ci, "REVIEW_KEYS", ())


def _repo():
    repo = Repo(BASE, "Test {carts} \"shelf\"")
    repo.add("snake", name="Snake", runtime="lua", modules=())
    repo.add("dm", name="Dungeon")
    repo.add("tricky", name='Brace } [ " \\ yourself', runtime="lua", modules=())
    repo.carts[-1]["description"] = 'It names "snake.moy" and {dm} in its text \\"'
    repo.revoke("snake", [7])
    return repo


def _read(net, url, folder, ident=None, own=None, read_from=None):
    job = ci.EntryRead(net, url, folder, ident, own, read_from)
    while job.step():
        pass
    return job.carts


def _shapes(repo):
    """The index as moybyte-org/carts writes it, and as a release writes
    its own (indented, keys sorted: `carts` before `version`)."""
    doc = json.loads(repo.index())
    return [repo.index(), json.dumps(doc, indent=2, sort_keys=True).encode() + b"\n"]


@pytest.mark.parametrize("k", [1, 3, 7, 64, 4096])
def test_the_entry_read_is_the_entry_parse_index_reads(k):
    repo = _repo()
    for data in _shapes(repo):
        whole = ci.parse_index(data, URL)
        for c in json.loads(data)["carts"]:
            got = _read(BitsNet({URL: data}, k), URL, c["folder"])
            assert got == [w for w in whole if w["folder"] == c["folder"]], (k, c["id"])
        assert _read(BitsNet({URL: data}, k), URL, "absent.moy") == []
        assert _read(BitsNet({URL: data}, k), URL, "snake.moy", "dm") == []
    snake = _read(BitsNet({URL: repo.index()}, 5), URL, "snake.moy")[0]
    assert snake["revoked"] == [7] and snake["shelf"] == 'Test {carts} "shelf"'


def test_a_signed_index_is_checked_over_its_streamed_digest(keys):
    repo = _repo()
    for data in _shapes(repo):
        signed = _sign(data)
        got = _read(BitsNet({URL: signed}, 13), URL, "snake.moy")
        assert got == [c for c in ci.parse_index(signed, URL) if c["id"] == "snake"]
        assert got[0]["signed"] is True and got[0]["reviewed"] is True
        assert _read(MemNet({URL: data}), URL, "snake.moy")[0]["signed"] is False
        for bad in (signed.replace(b'"Dungeon"', b'"Dungeom"'),
                    _sign(data, d=__import__("test_ota_signing").TEST_D + 2),
                    signed.replace(b', "sig": "', b', "sig": "', 1)[:-3] + b'0"}\n'):
            with pytest.raises(ci.InstallError) as exc:
                _read(MemNet({URL: bad}), URL, "snake.moy")
            assert exc.value.text == ci.BAD_SIGNATURE


def test_a_sig_that_is_not_the_last_member_is_refused(keys):
    doc = json.loads(_repo().index())
    doc = {"sig": "ab", "version": 1, "name": "x", "carts": doc["carts"]}
    with pytest.raises(ci.InstallError) as exc:
        _read(MemNet({URL: json.dumps(doc).encode()}), URL, "snake.moy")
    assert exc.value.text == ci.BAD_SIGNATURE


def test_what_is_not_an_index_is_refused():
    for bad in (b"[1, 2]", b'{"version": 1, "carts": [', b'{"version": 2, "carts": []}',
                b'{"version": 1}} ', b"not json"):
        with pytest.raises(ci.InstallError) as exc:
            _read(MemNet({URL: bad}), URL, "snake.moy")
        assert exc.value.text == ci.UNREACHABLE, bad
    with pytest.raises(ci.InstallError):
        _read(MemNet({}), URL, "snake.moy")


def test_an_entry_past_its_bound_is_left_unread(monkeypatch):
    repo = _repo()
    monkeypatch.setattr(ci, "ENTRY_MAX", max(len(json.dumps(c)) for c in repo.carts) + 8)
    repo.carts[1]["description"] = "x" * ci.ENTRY_MAX
    assert _read(MemNet({URL: repo.index()}), URL, "dm.moy") == []
    assert _read(MemNet({URL: repo.index()}), URL, "snake.moy")[0]["id"] == "snake"


def test_the_signature_with_keys_where_there_is_no_kernel(monkeypatch):
    """A page has no kernel: a signed index is unverified (None) unless the
    console's keys are given, which rsa_check's arithmetic checks."""
    monkeypatch.setattr(ci, "_native", lambda: None)
    monkeypatch.setattr(ci, "REVIEW_KEYS", ())
    data = _sign(_repo().index())
    assert ci.check_signature(data, URL) is None
    assert ci.check_signature(data, URL, TEST_KEYS) is True
    with pytest.raises(ci.InstallError):
        ci.check_signature(data.replace(b"Snake", b"Snakf"), URL, TEST_KEYS)


def test_rsa_check_is_the_kernel_s_verdict():
    from runtime import net_binding
    import rsa_check
    data = _sign(_repo().index())
    payload, sig = ci.split_signed(data)
    digest = hashlib.sha256(payload).digest()
    assert rsa_check.verify_digest(digest, sig, TEST_KEYS) is True
    assert net_binding.ota_verify_digest(digest, sig, TEST_KEYS) is True
    assert net_binding.ota_verify(payload, sig, TEST_KEYS) is True
    wrong = hashlib.sha256(payload + b" ").digest()
    assert rsa_check.verify_digest(wrong, sig, TEST_KEYS) is False
    assert net_binding.ota_verify_digest(wrong, sig, TEST_KEYS) is False


def test_the_release_index_is_mirrored_on_os_moybyte_com():
    import moy_ota
    rel = moy_ota._GH + "/firmware-latest/carts-c3_zero.json"
    assert rel.startswith(ci.RELEASES)
    assert ci.index_mirror(rel) == "https://os.moybyte.com/console/releases/" \
        "firmware-latest/carts-c3_zero.json"
    for other in (ci.DEFAULT_INDEXES[0], None, ci.RELEASES + "a/b/c.json",
                  ci.RELEASES + "../x.json", "http://192.168.1.2/carts-c3_zero.json"):
        assert ci.index_mirror(other) is None


def test_an_entry_read_from_the_mirror_is_stamped_with_the_release(keys):
    own = ci.RELEASES + "firmware-latest/carts-c3_zero.json"
    repo = _repo()
    signed = _sign(repo.index())
    mirror = ci.index_mirror(own)
    net = MemNet({mirror: signed})
    got = _read(net, own, "snake.moy", "snake", own, read_from=mirror)
    assert net.opened == [mirror]
    assert got[0]["index"] == own and got[0]["signed"] is True
    assert ci.resolve(got[0]["index"], "a.zip") == ci.RELEASES + "firmware-latest/a.zip"
