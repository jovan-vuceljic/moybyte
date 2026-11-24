"""The Editor's older layers hold no code only a test reaches: every function
and method they define is named somewhere a board stages (runtime/,
device/) besides its own definition. A seam a test wants is the page's
action (`run`), a stop's box or the layer's state, not a method kept for it."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULES = ("paint_layer", "theme_editor", "block_editor_ui", "editor_map",
           "editor_blocks", "editors_base")


def _shipped():
    return {p: p.read_text(encoding="utf-8").split("\n")
            for d in ("runtime", "device") for p in (ROOT / d).rglob("*.py")}


def _defs(tree):
    for n in tree.body:
        if isinstance(n, ast.FunctionDef):
            yield n
        elif isinstance(n, ast.ClassDef):
            for b in n.body:
                if isinstance(b, ast.FunctionDef):
                    yield b


def test_every_editor_layer_definition_is_named_by_shipped_code():
    texts = _shipped()
    unnamed = []
    for m in MODULES:
        (path,) = [p for p in texts if p.name == m + ".py"]
        for d in _defs(ast.parse("\n".join(texts[path]))):
            if d.name.startswith("__"):
                continue
            pat = re.compile(r"\b%s\b" % re.escape(d.name))
            if not any(pat.search(line) for p, lines in texts.items()
                       for i, line in enumerate(lines, 1)
                       if not (p == path and i == d.lineno)):
                unnamed.append("%s.%s" % (m, d.name))
    assert not unnamed, unnamed
