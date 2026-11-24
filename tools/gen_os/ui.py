# Map (grep -n a name to jump there):
#   Arg  one C parameter of a context-form verb and its kind
#   Verb  one face.json api row with its C prototype
#   verbs  every api row as a Verb
#   -- the context form, MicroPython  gen_mp: modmoy_ui_face.h
#   -- the context form, ctypes  gen_host: runtime/host/moy_ui_face.py
#   -- the parity probe  probe_calls, probe_script
#   -- the check  check: every hand face exists, no raw param on a generated one
#   outputs  every file this module writes, for tools/gen_os_table.py
"""The toolkit's engine verb faces (docs/refactor_2026-11/tiers.md section
2.2), from native/moy_ui/face.json's `api` rows, one per engine verb
(moy_ui_api.h's moy_ui_api_<verb>, its C prototype read from the header):
the context form the console's Python passes its own context to -- the
board module's `api_<verb>` (modmoy_ui_face.h) and the host's over ctypes
(runtime/host/moy_ui_face.py, with their argtypes).

An `api` row:
  api       the verb: the Python name api_<verb>, the C moy_ui_api_<verb>
  c         the C function where it is another (moy_ui_run_back)
  hand      true: both context faces are written by hand (the row only
            names them, and the check finds them); ["mp"] or ["host"]: that
            face alone
  ret       the Python answer where the C type does not say it: "bool",
            "nested" (MOY_UI_API_DEEP raises), "nested_none" (likewise,
            answering None), "if" (the out words' tuple where the C answered
            true, else None)
  out       {param: n}: int32 words the face makes and answers as a tuple
  buf       {param: n}: int32 words the caller passes (an array('i'))
  opts      [param]: a (bytes, length) pair a sequence may stand for (the
            boards' module joins it, modmoy_ui.c's opts_of)
  wspan     [param]: a (const int32_t *, int n) pair from an array('i')
  flag      [param]: an int the face takes as a truth value
  trunc     [param]: an int taken modulo its width
  dflt      {param: default}: the Python default
  doc       what the verb answers, where its prototype does not say it"""

import json
import os
import re

from . import TableError, header
from . import face as _face
from .face import Headers, NATIVE
from .table import ROOT

UI = os.path.join(NATIVE, "moy_ui")
FACE = os.path.join(UI, "face.json")
MP_C = os.path.join(UI, "modmoy_ui_face.h")
HOST_PY = os.path.join(ROOT, "runtime", "host", "moy_ui_face.py")
HAND_MP = os.path.join(UI, "modmoy_ui.c")
HAND_HOST = os.path.join(ROOT, "runtime", "host", "moy_ui_api_binding.py")

API_FIELDS = {"api", "c", "hand", "ret", "out", "buf", "opts", "wspan", "flag", "trunc", "dflt",
              "doc"}
# Python names a C parameter cannot keep on the host: the face calls these.
_PY_TAKEN = {"len", "int", "bytes", "bool", "tuple", "in", "c", "lib", "m"}
_UNSIGNED = {"uint32_t", "uint16_t", "uint8_t", "unsigned", "size_t"}
_CT = {"int": "c.c_int", "int32_t": "c.c_int32", "uint32_t": "c.c_uint32", "size_t": "c.c_size_t",
       "int16_t": "c.c_int16", "uint8_t": "c.c_uint8", "void": "None", "bool": "c.c_bool"}


def _fold(line, width=99, held=None):
    """A C line longer than `width` broken at the shallowest ", " that fits
    (the last of those), the rest under the parenthesis or brace open there;
    `held` the column of one a line it continues left open."""
    if len(line) <= width or line.lstrip().startswith("//"):
        return [line]
    stack, best = [] if held is None else [held], None
    for i, ch in enumerate(line):
        if ch in "({":
            stack.append(i)
        elif ch in ")}" and stack:
            stack.pop()
        elif ch == "," and i + 1 < width and stack and line[i + 1:i + 2] == " ":
            key = (-len(stack), i)
            if best is None or key > best[0]:
                best = (key, i, stack[-1])
    if best is None:
        return [line]
    _k, i, at = best
    return [line[:i + 1]] + _fold(" " * (at + 1) + line[i + 2:], width, at)


def fold(text):
    return "\n".join(x for line in text.split("\n") for x in _fold(line))


def load():
    with open(FACE) as f:
        rows = json.load(f)["moy_ui"].get("api", [])
    return rows


def _base(t):
    return re.sub(r"\s+", " ", re.sub(r"\bconst\b", "", t)).strip()


def _split_param(p):
    m = re.match(r"^(.*?)\b(\w+)\s*(?:\[(\w*)\])?$", p.strip())
    if not m:
        raise TableError("no parameter in %r" % p)
    return m.group(1).strip(), m.group(2), m.group(3)


class Arg:
    """One C parameter of an engine verb, as the faces take it."""

    def __init__(self, kind, cn, ct, arr=None, n=None, py=(), pair=None):
        self.kind, self.cn, self.ct, self.arr, self.n = kind, cn, ct, arr, n
        self.py = list(py)              # the Python parameters it consumes
        self.pair = pair                # a (pointer, length) pair's length decl

    def decl(self, name=None):
        name = name or self.cn
        return "%s%s%s%s" % (self.ct, "" if self.ct.endswith("*") else " ", name,
                             "[%s]" % self.arr if self.arr is not None else "")


class Verb:
    """An `api` row and its engine verb's prototype."""

    def __init__(self, row, hdr):
        bad = set(row) - API_FIELDS
        if bad:
            raise TableError("moy_ui api %s: %s" % (row.get("api"), ", ".join(sorted(bad))))
        self.row = row
        self.verb = row["api"]
        self.name = "api_" + self.verb
        self.fn = row.get("c", "moy_ui_api_" + self.verb)
        hand = row.get("hand", False)
        self.hand = {"mp", "host"} if hand is True else set(hand or ())
        self.args = None
        self.why = None
        self.ret, self.params = "void", []
        try:
            ret, _fn, ps, _ = hdr.proto(self.fn)
            self.ret = ret.strip()
            self.params = [_split_param(p) for p in ps if p.strip() not in ("", "void")]
            self.args = self._classify()
        except TableError as e:
            if self.hand != {"mp", "host"}:
                raise
            self.why = str(e)
        dflt = row.get("dflt", {})
        self.py = [] if self.args is None else [p for a in self.args for p in a.py]
        self.dflt = [dflt.get(p) for p in self.py]

    def _classify(self):
        row = self.row
        out, buf = row.get("out", {}), row.get("buf", {})
        opts, wspan = set(row.get("opts", ())), set(row.get("wspan", ()))
        flag, trunc = set(row.get("flag", ())), set(row.get("trunc", ()))
        args, i, ps = [], 0, self.params
        while i < len(ps):
            ct, cn, arr = ps[i]
            b = _base(ct)
            nxt = _base(ps[i + 1][0]) if i + 1 < len(ps) else None
            py = cn + "_" if cn in _PY_TAKEN else cn
            if b == "moy_ui_ctx_t *":
                args.append(Arg("ctx", cn, ct, py=["ctx"]))
            elif b == "moy_ui_inst_t *":
                args.append(Arg("inst", cn, ct))
            elif b == "moy_ui_sink_t *":
                args.append(Arg("sink", cn, ct, py=["cv", "look"]))
            elif b == "moy_ui_span_t":
                args.append(Arg("span", cn, ct, py=[py]))
            elif b == "moy_ui_over_t *":
                args.append(Arg("over", cn, ct, py=[py]))
            elif b == "moy_ui_box_t":
                args.append(Arg("box", cn, ct, py=[py]))
            elif b == "moy_ui_box_t *":
                args.append(Arg("boxout", cn, ct))
            elif b == "uint8_t *" and nxt == "size_t":
                kind = "opts" if cn in opts else "bytes" if ct.startswith("const") else "rw"
                args.append(Arg(kind, cn, ct, py=[py], pair=ps[i + 1]))
                i += 1
            elif b in ("int32_t *", "int32_t") and (arr is not None or b.endswith("*")) \
                    and cn in wspan:
                args.append(Arg("wspan", cn, ct, arr, py=[py], pair=ps[i + 1]))
                i += 1
            elif (b == "int32_t *" or (b == "int32_t" and arr is not None)) and cn in out:
                args.append(Arg("out", cn, ct, arr, n=out[cn]))
            elif (b == "int32_t *" or (b == "int32_t" and arr is not None)) and cn in buf:
                args.append(Arg("buf", cn, ct, arr, n=buf[cn], py=[py]))
            elif arr is None and b in ("int", "int32_t", "uint32_t", "size_t", "bool"):
                kind = "flag" if cn in flag else "trunc" if (cn in trunc or b in ("uint32_t",)) \
                    else "int"
                args.append(Arg(kind, cn, ct, py=[py]))
            else:
                args.append(Arg("raw", cn, ct, arr))     # the RUN form passes it on
            i += 1
        rb = _base(self.ret)
        if rb not in ("void", "int", "int32_t", "uint32_t", "size_t", "moy_ui_box_t", "char *",
                      "bool"):
            raise TableError("moy_ui %s: no answer for %s" % (self.verb, self.ret))
        if [a for a in args if a.kind == "out"] and len([a for a in args if a.kind == "out"]) > 1:
            raise TableError("moy_ui %s: one out" % self.verb)
        return args

    def has(self, kind):
        return any(a.kind == kind for a in self.args or ())

    @property
    def answers(self):
        """Whether the Python verb answers something."""
        rb = _base(self.ret)
        r = self.row.get("ret")
        if r == "nested_none":
            return False
        return rb != "void" or self.has("out") or self.has("boxout")


def verbs(hdr=None):
    hdr = hdr or Headers({"dir": "moy_ui", "headers": ["moy_ui_api.h", "moy_ui_run.h"]})
    return [Verb(r, hdr) for r in load()]


# ---- the context form, MicroPython ----------------------------------------------

def _mp_conv(a, x):
    b = _base(a.ct)
    if a.kind == "flag":
        return "mp_obj_is_true(%s)" % x
    if a.kind == "trunc":
        return "(%s)mp_obj_get_int_truncated(%s)" % (b, x)
    if b == "size_t":
        return "(size_t)num(%s)" % x
    return "num(%s)" % x


def _mp_row(v):
    fn = "ui_api_" + v.verb
    n = len(v.py)
    need = sum(1 for d in v.dflt if d is None)
    var = n > 3 or need != n
    if var:
        o = ["static mp_obj_t %s(size_t n_args, const mp_obj_t *a) {" % fn]
        if need == n:
            o.append("    (void)n_args;")
        arg = ["a[%d]" % i for i in range(n)]
    else:
        o = ["static mp_obj_t %s(%s) {" % (fn, ", ".join("mp_obj_t a%d" % i for i in range(n))
                                           or "void")]
        arg = ["a%d" % i for i in range(n)]
    k = 0
    call = []
    post = None
    for a in v.args:
        x = arg[k:k + len(a.py)]
        if a.kind == "ctx":
            o.append("    moy_ui_ctx_t *%s = ctx_of(%s);" % (a.cn, x[0]))
            call.append(a.cn)
        elif a.kind == "inst":
            call.append("NULL")
        elif a.kind == "sink":
            o.append("    moy_ui_sink_t %s;" % a.cn)
            o.append("    sink_of(&%s, %s, %s);" % (a.cn, x[0], x[1]))
            call.append("&" + a.cn)
        elif a.kind == "span":
            call.append("span0_of(%s)" % x[0])
        elif a.kind == "over":
            o.append("    moy_ui_over_t %s_v;" % a.cn)
            call.append("over_of(%s, &%s_v)" % (x[0], a.cn))
        elif a.kind == "box":
            call.append("box_of(%s)" % x[0])
        elif a.kind == "boxout":
            o.append("    moy_ui_box_t %s;" % a.cn)
            call.append("&" + a.cn)
            post = "    return box_tuple(%s);" % a.cn
        elif a.kind in ("opts", "bytes", "rw"):
            o.append("    mp_buffer_info_t %s_b;" % a.cn)
            if a.kind == "opts":
                o.append("    uint8_t %s_ob[OPTS_BUF];" % a.cn)
                o.append("    opts_of(%s, %s_ob, &%s_b);" % (x[0], a.cn, a.cn))
            else:
                o.append("    mp_get_buffer_raise(%s, &%s_b, MP_BUFFER_%s);"
                         % (x[0], a.cn, "READ" if a.kind == "bytes" else "RW"))
            call += ["(%s)%s_b.buf" % (a.ct, a.cn), "%s_b.len" % a.cn]
        elif a.kind == "wspan":
            o.append("    mp_buffer_info_t %s_b;" % a.cn)
            o.append("    mp_get_buffer_raise(%s, &%s_b, MP_BUFFER_READ);" % (x[0], a.cn))
            call += ["(const int32_t *)%s_b.buf" % a.cn, "(int)(%s_b.len / 4)" % a.cn]
        elif a.kind == "out":
            o.append("    int32_t %s[%d];" % (a.cn, a.n))
            call.append(a.cn)
            items = ", ".join("mp_obj_new_int(%s[%d])" % (a.cn, j) for j in range(a.n))
            post = ["    mp_obj_t t_[%d] = {%s};" % (a.n, items),
                    "    return ret_tuple(%d, t_);" % a.n]
        elif a.kind == "buf":
            w = 0 if a.ct.startswith("const") else 1
            o.append("    %sint32_t *%s = words_of(%s, %d, %d, MP_ERROR_TEXT(\"moy_ui: %d words\"));"
                     % ("const " if not w else "", a.cn, x[0], a.n, w, a.n))
            call.append(a.cn)
        else:
            dflt = v.dflt[k]
            e = _mp_conv(a, x[0])
            if var and dflt is not None:
                e = "n_args > %d ? %s : %s" % (k, e, dflt)
            call.append(e)
        k += len(a.py)
    cx = "%s(%s)" % (v.fn, ", ".join(call))
    ret = v.row.get("ret")
    rb = _base(v.ret)
    if ret == "if":
        o.append("    if (!%s) {" % cx)
        o.append("        return mp_const_none;")
        o.append("    }")
        o += post
    elif post is not None:
        o.append("    %s;" % cx)
        o += post if isinstance(post, list) else [post]
    elif ret == "nested":
        o.append("    return mp_obj_new_int(nested(%s));" % cx)
    elif ret == "nested_none":
        o.append("    nested(%s);" % cx)
        o.append("    return mp_const_none;")
    elif rb == "void":
        o.append("    %s;" % cx)
        o.append("    return mp_const_none;")
    elif ret == "bool" or rb == "bool":
        o.append("    return mp_obj_new_bool(%s);" % cx)
    elif rb == "moy_ui_box_t":
        o.append("    return box_tuple(%s);" % cx)
    elif rb == "char *":
        o.append("    const char *r_ = %s;" % cx)
        o.append("    return r_ == NULL ? mp_const_none : ret_str(r_, strlen(r_));")
    elif rb in ("uint32_t", "size_t"):
        o.append("    return mp_obj_new_int_from_uint(%s);" % cx)
    else:
        o.append("    return mp_obj_new_int(%s);" % cx)
    o.append("}")
    if var:
        o.append("static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(%s_obj, %d, %d, %s);"
                 % (fn, need, n, fn))
    else:
        o.append("static MP_DEFINE_CONST_FUN_OBJ_%d(%s_obj, %s);" % (n, fn, fn))
    return o


def gen_mp(vs):
    o = [header("native/moy_ui/face.json", "//"),
         "// The board module's context form of the toolkit's verbs (`api_<verb>`), included",
         "// by modmoy_ui.c after its converters: MOY_FACE_MOY_UI_ROWS is their part of its",
         "// globals table. Each takes the app's context, the canvas and look it draws in",
         "// where it draws, its arguments, and `o` the override dict or block.", ""]
    for v in vs:
        if "mp" in v.hand:
            continue
        o += _mp_row(v)
        o.append("")
    o.append("#define MOY_FACE_MOY_UI_ROWS \\")
    ent = ["    { MP_ROM_QSTR(MP_QSTR_%s), MP_ROM_PTR(&ui_%s_obj) }" % (v.name, v.name)
           for v in vs if "mp" not in v.hand]
    o += [e + ", \\" for e in ent[:-1]] + [ent[-1] + ",", ""]
    return "\n".join(o)


# ---- the context form, ctypes ----------------------------------------------------

def _ctype(a):
    b = _base(a.ct)
    if a.kind in ("ctx", "inst", "over", "rw", "out", "buf", "wspan"):
        return "c.c_void_p"
    if a.kind == "sink":
        return "c.POINTER(moy_ui_sink_t)"
    if a.kind == "span":
        return "moy_ui_span_t"
    if a.kind == "box":
        return "moy_ui_box_t"
    if a.kind == "boxout":
        return "c.POINTER(moy_ui_box_t)"
    if a.kind in ("opts", "bytes"):
        return "c.c_char_p"
    return _CT[b]


def _restype(v):
    rb = _base(v.ret)
    if rb == "moy_ui_box_t":
        return "moy_ui_box_t"
    if rb == "char *":
        return "c.c_char_p"
    return _CT[rb]


def _sig(v):
    ts = []
    for a in v.args:
        ts.append(_ctype(a))
        if a.pair is not None:
            ts.append(_CT[_base(a.pair[0])])
    return '    ("%s", [%s], %s),' % (v.fn, ", ".join(ts), _restype(v))


def _py_row(v):
    ps = [p if d is None else "%s=%s" % (p, d) for p, d in zip(v.py, v.dflt)]
    o = ["    def %s(%s):" % (v.name, ", ".join(ps))]
    call, post = [], None
    for a in v.args:
        x = a.py
        if a.kind == "ctx":
            o.append("        p_, k_ = ctx_(ctx)")
            call.append("p_")
        elif a.kind == "inst":
            call.append("None")
        elif a.kind == "sink":
            call.append("c.byref(sink(cv, look))")
        elif a.kind == "span":
            o.append("        %s_t, %s_k = span0(%s)" % (a.cn, a.cn, x[0]))
            call.append("%s_t" % a.cn)
        elif a.kind == "over":
            o.append("        %s_v, %s_k = over(%s)" % (a.cn, a.cn, x[0]))
            call.append("%s_v" % a.cn)
        elif a.kind == "box":
            call.append("box_of(%s)" % x[0])
        elif a.kind == "boxout":
            o.append("        %s = moy_ui_box_t()" % a.cn)
            call.append("c.byref(%s)" % a.cn)
            post = "        return (%s.x, %s.y, %s.w, %s.h)" % ((a.cn,) * 4)
        elif a.kind in ("opts", "bytes"):
            o.append("        %s_b = bytes(%s)" % (a.cn, x[0]))
            call += ["%s_b" % a.cn, "len(%s_b)" % a.cn]
        elif a.kind == "rw":
            o.append("        %s_b = (c.c_uint8 * max(1, len(%s))).from_buffer(%s) if len(%s) "
                     "else (c.c_uint8 * 1)()" % (a.cn, x[0], x[0], x[0]))
            call += ["%s_b" % a.cn, "len(%s)" % x[0]]
        elif a.kind == "wspan":
            o.append("        %s_w = (c.c_int32 * len(%s))(*%s)" % (a.cn, x[0], x[0]))
            call += ["%s_w" % a.cn, "len(%s)" % x[0]]
        elif a.kind == "out":
            o.append("        %s_w = (c.c_int32 * %d)()" % (a.cn, a.n))
            call.append("%s_w" % a.cn)
            post = "        return tuple(%s_w)" % a.cn
        elif a.kind == "buf":
            call.append("(c.c_int32 * %d).from_buffer(%s)" % (a.n, x[0]))
        elif a.kind == "flag":
            call.append("1 if %s else 0" % x[0])
        else:
            call.append("int(%s)" % x[0])
    cx = "lib.%s(%s)" % (v.fn, ", ".join(call))
    ret = v.row.get("ret")
    rb = _base(v.ret)
    if ret == "if":
        o.append("        if not %s:" % cx)
        o.append("            return None")
        o.append(post)
    elif post is not None:
        o.append("        " + cx)
        o.append(post)
    elif ret == "nested":
        o.append("        return _nested(int(%s))" % cx)
    elif ret == "nested_none":
        o.append("        _nested(int(%s))" % cx)
    elif rb == "void":
        o.append("        " + cx)
    elif ret == "bool" or rb == "bool":
        o.append("        return bool(%s)" % cx)
    elif rb == "moy_ui_box_t":
        o.append("        b_ = %s" % cx)
        o.append("        return (b_.x, b_.y, b_.w, b_.h)")
    elif rb == "char *":
        o.append("        r_ = %s" % cx)
        o.append("        return None if r_ is None else r_.decode(\"utf-8\", \"replace\")")
    else:
        o.append("        return int(%s)" % cx)
    o.append("    m.%s = %s" % (v.name, v.name))
    return o


def gen_host(vs):
    o = [header("native/moy_ui/face.json", "#"),
         '"""The host\'s context form of the toolkit\'s verbs over ctypes: the argtypes',
         "of each engine verb they call (SIGS, which runtime/host/moy_ui_binding.py",
         "sets), and the verbs, set on the module by runtime/host/moy_ui_api_binding.py's",
         'install with its converters; and the ctypes mirrors of the structures the',
         'toolkit\'s host binding reads (tools/gen_os/structs.py)."""', "",
         "import ctypes as c", "import ctypes as _c", "", ""] + _face.mirrors(_face.load()["moy_ui"]).emit() + [
         "SIGS = ("]
    o += [_sig(v) for v in vs if v.args is not None and v.hand != {"mp", "host"}]
    o += [")", "", "",
          "def install(m, lib, ctx_, sink, span0, over, box_of):",
          '    """The verbs on module `m` over `lib`: `ctx_` a context\'s pointer and what',
          "    keeps it, `sink` a canvas's sink, `span0` a text's span (None as \"\"), `over`",
          '    the override block\'s struct and what keeps it, `box_of` a rect."""',
          "    from runtime.moy_ui_binding import _nested"]
    for v in vs:
        if "host" not in v.hand:
            o += _py_row(v)
    o.append("")
    return "\n".join(o)


# ---- the parity probe --------------------------------------------------------------

_NESTS = {"scroll": 5, "grid": 7, "group": 5, "popover": 6}
_PROBE = {"ctx": ["CTX"], "sink": ["CV", "None"], "span": ['"probe"'], "over": ["OV"],
          "opts": ['b"one\\x00two\\x00three"'], "bytes": ['b"pasted"'],
          "rw": ["bytearray(b'abc' + bytes(29))"], "wspan": ["array('i', [0, -1, 0, 75, 4, 0])"],
          "box": ["(0, 0, 100, 40)"], "flag": ["True"], "trunc": ["7"], "int": ["3"]}


def probe_calls(vs=None):
    """[(name, [argument text])]: each generated context-form row called on
    arguments made from its C types, a nest it opens closed after it."""
    out = []
    for v in vs or verbs():
        if v.args is None or v.hand or v.verb == "size" or (v.verb.startswith("run_")
                                                            and v.verb != "run_typing"):
            continue
        args = []
        for a in v.args:
            if a.kind == "buf":
                args.append("array('i', [0] * %d)" % a.n)
            else:
                args += _PROBE.get(a.kind, [])
        out.append((v.name, args))
        if v.verb == "dialog":
            out.append((v.name, ["CTX", "CV", "None", '""', 'b""', "0", "None"]))
        elif v.verb in _NESTS:
            out.append((v.name, ["CTX", "CV", "None", '""'] + ["0"] * (_NESTS[v.verb] - 5)
                        + ["None"]))
    return out


def probe_script(vs=None):
    """The context form's probe, run where `M` is the module, `CTX` a context
    begun by `begin()`, `CV` a canvas, `OV` an override block: three frames of
    every generated row, each answer printed."""
    o = ["def out(name, f):", "    try:", "        r = f()", "    except Exception as e:",
         "        r = 'EXC ' + type(e).__name__", "    print(name, repr(r))", "",
         "for f in range(3):", "    begin()"]
    o += ["    out(%r, lambda: M.%s(%s))" % (n, n, ", ".join(a)) for n, a in probe_calls(vs)]
    o += ["print('DONE')", ""]
    return "\n".join(o)


# ---- the check ---------------------------------------------------------------------

def check(vs):
    seen = set()
    for v in vs:
        if v.verb in seen:
            raise TableError("moy_ui api %s twice" % v.verb)
        seen.add(v.verb)
        for a in v.args or ():
            if a.kind == "raw" and v.hand != {"mp", "host"}:
                raise TableError("moy_ui api %s: no face for %s %s" % (v.verb, a.ct, a.cn))
    with open(HAND_MP) as f:
        mp = f.read()
    with open(HAND_HOST) as f:
        host = f.read()
    for v in vs:
        if "mp" in v.hand and not re.search(r"\bui_%s_obj\b" % v.name, mp):
            raise TableError("moy_ui %s: no hand MicroPython face" % v.name)
        if "host" in v.hand and not re.search(r"\bdef %s\(" % v.name, host):
            raise TableError("moy_ui %s: no hand ctypes face" % v.name)


def outputs():
    """The context form's two faces."""
    vs = verbs()
    check(vs)
    return [(MP_C, fold(gen_mp(vs))), (HOST_PY, fold(gen_host(vs)))]
