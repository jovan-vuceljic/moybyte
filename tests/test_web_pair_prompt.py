"""What the page's pairing card says (firmware/web_runner/page_tail.js,
pinAsk), run in node over a stand-in for its elements: a screenless board
with no password yet, reached without its claim (#331), says so, why its SSH
is off and how to set one, never "pair by cable" alone."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _card(m, claim=None):
    """(heading, prompt, the password field's row shown) after pinAsk(m)."""
    tail = (ROOT / "firmware/web_runner/page_tail.js").read_text(encoding="utf-8")
    nopw = re.search(r"^var NOPW=.*?;$", tail, re.M | re.S).group(0)
    ask = re.search(r"^function pinAsk\(m\)\{.*?(?=^function pinSubmit)", tail,
                    re.M | re.S).group(0)
    js = ("const el=()=>({textContent:'',style:{},className:'',disabled:true,value:'',"
          "focus(){}});\n"
          "var PINEL=el(),PINF=el(),PINB=el(),PINM=el(),PINP=el(),PINR=el(),PINH=el();\n"
          "var CLAIM=%s,CHOOSE=false,TAKEN=false;\nfunction asApp(){return false;}\n"
          "%s\n%s\npinAsk(%s);\n"
          "console.log(JSON.stringify([PINH.textContent,PINP.textContent,"
          "PINR.style.display!=='none']));\n" % (json.dumps(claim), nopw, ask, json.dumps(m)))
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_a_board_with_no_password_says_so_and_how_to_set_one():
    head, said, field = _card({"pw": False, "cable": True, "why": "", "wait": ""})
    assert head == "no password yet" and not field
    assert "no password yet" in said and "SSH" in said and "Manage by cable" in said, said


def test_its_claim_asks_for_the_first_password_and_one_set_is_typed():
    _, said, field = _card({"pw": False, "cable": True, "why": "", "wait": ""},
                           claim={"claim": "0" * 32, "id": ""})
    assert said.startswith("Choose this console's password") and field
    head, said, field = _card({"pw": True, "cable": True, "why": "", "wait": ""})
    assert head == "pair this browser" and said.startswith("Type the console's password") and field
