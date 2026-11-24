"""The app guide's code is the code that runs (docs/app_api_v1.md sections 1,
3 and 4): every example it shows is a file a test runs, shown verbatim but
for its leading comment (section 4's second page a run of one), the first
app is what `moy app new` writes on each tier, and its error table is the
contract's codes, each with its meaning and fix
(native/moy_uitree/contract.json)."""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "sdk"))

from moybyte_sdk import templates  # noqa: E402

GUIDE = os.path.join(ROOT, "docs", "app_api_v1.md")
COUNTER = "tests/uitree_conformance/counter/"

# each shown example, and the test that runs it
EXAMPLES = (
    COUNTER + "counter_py.moy/manifest.json",               # test_uitree_conformance.py
    COUNTER + "counter_py.moy/main.py",
    COUNTER + "counter.moy/main.lua",
    COUNTER + "counter_wasm.moy/src/main.c",
    "tests/fixtures/apps/shopping.moy/main.py",              # test_app_examples.py
    "tests/uitree_conformance/list/list.moy/main.lua",       # test_uitree_conformance.py
)
LANG = {".py": "python", ".lua": "lua", ".c": "c", ".json": "json"}
COMMENT = {".py": "#", ".lua": "--", ".c": "//", ".json": "//"}


def shown(rel):
    """The file at `rel` as the guide shows it: its leading comment gone."""
    with open(os.path.join(ROOT, rel)) as f:
        lines = f.read().split("\n")
    i = 0
    lead = COMMENT[os.path.splitext(rel)[1]]
    while i < len(lines) and lines[i].startswith(lead):
        i += 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    return "\n".join(lines[i:])


def block(rel):
    return "```%s\n%s```" % (LANG[os.path.splitext(rel)[1]], shown(rel))


def error_rows():
    """The error table's rows: every code of the contract, its meaning and
    its fix (Python's, else Lua's, else C's)."""
    with open(os.path.join(ROOT, "native", "moy_uitree", "contract.json")) as f:
        codes = json.load(f)["codes"]
    rows = ["| code | the mistake | the fix |", "|---|---|---|"]
    for code in sorted(codes):
        fix = codes[code]["fix"]
        best = next((fix[t] for t in ("python", "lua", "c") if fix[t] != "—"), "—")
        rows.append("| %s | %s | %s |" % (code, codes[code]["meaning"].replace("|", "\\|"),
                                          best.replace("|", "\\|")))
    return rows


def _guide():
    with open(GUIDE) as f:
        return f.read()


@pytest.mark.parametrize("rel", EXAMPLES)
def test_every_example_is_a_file_a_test_runs(rel):
    assert block(rel) in _guide(), "docs/app_api_v1.md no longer shows %s as it is" % rel


def test_the_second_page_is_the_fixture_s():
    guide = _guide()
    at = guide.index("```python\n", guide.index("A second page is a page function"))
    snippet = guide[at + len("```python\n"):guide.index("```", at + 3)]
    with open(os.path.join(ROOT, "tests", "uitree_conformance", "pages", "app.py")) as f:
        assert snippet in f.read()


@pytest.mark.parametrize("template,rel,subs", [
    (templates.PY_APP, COUNTER + "counter_py.moy/main.py", {"title_str": '"Counter"'}),
    (templates.LUA_APP, COUNTER + "counter.moy/main.lua", {"title_str": '"Counter"'}),
    (templates.WASM_APP, COUNTER + "counter_wasm.moy/src/main.c", {"title_c": "Counter"}),
])
def test_the_first_app_is_the_template(template, rel, subs):
    assert template % subs == shown(rel)


def test_the_error_table_is_the_contract_s():
    lines = [x for x in _guide().split("\n") if x.startswith("| code | the mistake |")]
    assert len(lines) == 1
    got = _guide().split("\n")
    i = got.index(lines[0])
    want = error_rows()
    assert got[i:i + len(want)] == want
    assert not got[i + len(want)].startswith("|")
