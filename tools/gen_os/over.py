"""The override table's readers, from native/moy_ui/over.json: the keys and
the block's bits for the C (moy_ui_over_keys.h) and the board module's dict
keys (modmoy_ui_over.h)."""

import json
import os

from . import TableError, header
from .table import ROOT

SRC = os.path.join(ROOT, "native", "moy_ui", "over.json")
KEYS_H = os.path.join(ROOT, "native", "moy_ui", "moy_ui_over_keys.h")
MP_H = os.path.join(ROOT, "native", "moy_ui", "modmoy_ui_over.h")

KINDS = ("colour", "tri", "flag", "wash", "axis", "int", "index", "pair", "quad", "text", "texts")
WHERE = ("head", "hint", "flags", "rows", "flags2")
WORDS = {"int": 1, "index": 1, "pair": 2, "quad": 4}
# The first flags word's bits no key owns: `wash` not given, `wash` "view",
# a list's two-line rows (their word of MOY_UI_OR_* follows) and the second
# flags word (MOY_UI_O2_*) after the focus's text.
BITS = {"NO_WASH": 3, "WASH_VIEW": 24, "ROWS": 25, "MORE": 29}


def load():
    with open(SRC) as f:
        keys = json.load(f)["keys"]
    check(keys)
    return keys


def _rank(k):
    """A key's place in the block: the head's words, the hint, the first
    flags word's bits (the rows' at bit 25), the second word's."""
    w = k["where"]
    if w == "head":
        return (0, 0)
    if w == "hint":
        return (1, 0)
    if w == "flags":
        return (2, k["bit"])
    if w == "rows":
        return (2, BITS["ROWS"])
    return (3, k["bit"])


def check(keys):
    seen, bits = set(), {}
    for b, n in BITS.items():
        bits[("flags", n)] = b
    last = (0, 0)
    for k in keys:
        name = k["key"]
        if name in seen:
            raise TableError("over.json: %s twice" % name)
        seen.add(name)
        if k["kind"] not in KINDS or k["where"] not in WHERE:
            raise TableError("over.json: %s: kind %s, where %s" % (name, k["kind"], k["where"]))
        if k["where"] in ("flags", "rows", "flags2"):
            at = (k["where"], k["bit"])
            if at in bits or not 0 <= k["bit"] <= (30 if k["where"] != "rows" else 15):
                raise TableError("over.json: %s: bit %s" % (name, k["bit"]))
            bits[at] = name
        if _rank(k) < last:
            raise TableError("over.json: %s is out of the block's order" % name)
        last = _rank(k)
        if k["where"] == "head" and k["kind"] not in ("colour", "tri", "text"):
            raise TableError("over.json: %s: the head holds colours, flags and the id" % name)
        if k["where"] == "rows" and k["kind"] != "texts":
            raise TableError("over.json: %s: a row key is a list of texts" % name)
        if k["where"] == "flags2" and k["kind"] != "flag":
            raise TableError("over.json: %s: the second flags word carries no words yet" % name)
        if "doc" in k:
            if k["doc"] not in seen:
                raise TableError("over.json: %s shares the row of %s, before it" % (name, k["doc"]))
        elif not k.get("value") or not k.get("does"):
            raise TableError("over.json: %s has no doc row" % name)
        if "probe" not in k or "example" not in k:
            raise TableError("over.json: %s: no probe" % name)
    if [k["where"] for k in keys if k["where"] == "hint"] != ["hint"]:
        raise TableError("over.json: one hint key")


def _cname(k):
    return k["key"].upper()


def gen_keys_h(keys):
    o = [header("native/moy_ui/over.json", "//"),
         "// The override table's keys, their order the block's (moy_ui_api.h's",
         "// moy_ui_over_block): every tier's reader walks moy_ui_over_keys.",
         "#ifndef MOY_UI_OVER_KEYS_H",
         "#define MOY_UI_OVER_KEYS_H",
         "",
         "#include <stdint.h>",
         "",
         "// A key, its index in moy_ui_over_keys.",
         "enum {"]
    o += ["    MOY_UI_OV_%s," % _cname(k) for k in keys]
    o += ["    MOY_UI_OV_COUNT", "};", "",
          "// A key's value (`kind`): a role's name or an RGB colour; true, false or",
          "// absent; true sets it; true, false or \"view\"; \"x\"; a number (a Lua",
          "// index from 1); two numbers; four; a text; a list of texts NUL-joined.",
          "enum {"]
    o += ["    MOY_UI_KIND_%s," % k.upper() for k in KINDS]
    o += ["};", "",
          "// Where its value sits in the block (`where`): a word of the nine (the",
          "// id's, its text's length, the text after them), the word after them, a",
          "// bit of the first flags word (its words after the flags in its bits'",
          "// order), a bit of the rows' word (MOY_UI_O_ROWS), a bit of the second",
          "// flags word (MOY_UI_O_MORE).",
          "enum {"]
    o += ["    MOY_UI_AT_%s," % w.upper() for w in WHERE]
    o += ["};", "", "// The nine words' indices.", "enum {"]
    head = [k for k in keys if k["where"] == "head"]
    o += ["    MOY_UI_O_%s%s," % (_cname(k), " = 0" if i == 0 else "") for i, k in enumerate(head)]
    o += ["    MOY_UI_O_WORDS", "};", "", "// The first flags word's bits."]
    bits = [(k["bit"], _cname(k)) for k in keys if k["where"] == "flags"]
    bits += [(n, b) for b, n in BITS.items()]
    o += ["#define MOY_UI_O_%s 0x%x" % (name, 1 << b) for b, name in sorted(bits)]
    o += ["// The rows' word's bits."]
    o += ["#define MOY_UI_OR_%s 0x%x" % (_cname(k), 1 << k["bit"])
          for k in keys if k["where"] == "rows"]
    o += ["// The second flags word's bits."]
    o += ["#define MOY_UI_O2_%s 0x%x" % (_cname(k), 1 << k["bit"])
          for k in keys if k["where"] == "flags2"]
    o += ["",
          "typedef struct {",
          "    const char *name;",
          "    uint8_t kind, where, bit;           // MOY_UI_KIND_*, MOY_UI_AT_*; its bit (0 in the head)",
          "} moy_ui_over_key_t;",
          "",
          "#define MOY_UI_OVER_KEYS { \\"]
    for k in keys:
        o.append("    {\"%s\", MOY_UI_KIND_%s, MOY_UI_AT_%s, %d}, \\"
                 % (k["key"], k["kind"].upper(), k["where"].upper(), k.get("bit", 0)))
    o += ["}", "", "#endif", ""]
    return "\n".join(o)


def gen_mp_h(keys):
    o = [header("native/moy_ui/over.json", "//"),
         "// The override dict's keys for modmoy_ui.c's over_dict: a key's index in",
         "// moy_ui_over_keys (moy_ui_over_keys.h) by its qstr, -1 for none.",
         "static int over_slot(qstr q) {",
         "    switch (q) {"]
    o += ["        case MP_QSTR_%s: return MOY_UI_OV_%s;" % (k["key"], _cname(k)) for k in keys]
    o += ["        default: return -1;", "    }", "}", ""]
    return "\n".join(o)


def outputs():
    keys = load()
    return [(KEYS_H, gen_keys_h(keys)), (MP_H, gen_mp_h(keys))]
