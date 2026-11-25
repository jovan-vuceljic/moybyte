"""tools/patch_mdns_psram.py: the responder's scratch becomes a PSRAM block
and its task a PSRAM stack, each group every hunk or none, and a tree that
carries the scratch group takes the stack group on its own."""

import pytest

from tools import patch_mdns_psram as p

# Each hunk's stock text once, in a file of the component's shape.
STOCK = "".join(stock + "\n" for stock, _ in p.HUNKS + p.STACK_HUNKS[1:]) \
    + p.PARSE_HEAD + p.PARSE_USE + "}\n"


def _tree(tmp_path, text):
    f = tmp_path / p.FILE
    f.parent.mkdir(parents=True)
    f.write_text(text, encoding="utf-8")
    return f


def test_a_stock_tree_takes_the_scratch_and_the_stack(tmp_path):
    f = _tree(tmp_path, STOCK)
    assert p.apply(str(tmp_path)) == "patched"
    out = f.read_text(encoding="utf-8")
    assert p.MARKER in out and p.STACK_MARKER in out
    assert "xTaskCreatePinnedToCoreWithCaps(" in out and "MOY_MDNS_STACK_CAPS);" in out
    assert "vTaskDelete(" not in out.replace("vTaskDeleteWithCaps(", "")
    assert "mdns_name_t *name = moy_name;" in out


def test_a_tree_with_the_scratch_alone_takes_the_stack(tmp_path):
    f = _tree(tmp_path, p.patch_text(STOCK))
    assert p.apply(str(tmp_path)) == "patched"
    out = f.read_text(encoding="utf-8")
    assert out.count(p.MARKER) == 1 and p.STACK_MARKER in out


def test_a_patched_tree_is_left_as_it_is(tmp_path):
    f = _tree(tmp_path, STOCK)
    p.apply(str(tmp_path))
    once = f.read_text(encoding="utf-8")
    assert p.apply(str(tmp_path)) == "already"
    assert f.read_text(encoding="utf-8") == once


def test_a_component_that_changed_shape_is_refused_and_not_written(tmp_path):
    f = _tree(tmp_path, STOCK.replace("    vTaskDelete(NULL);\n", "    vTaskDelete( NULL );\n"))
    before = f.read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        p.apply(str(tmp_path))
    assert f.read_text(encoding="utf-8") == before
