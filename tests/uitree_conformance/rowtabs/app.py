"""Conformance fixture `rowtabs` (level 2), the Python half: tabs over a
row_of, a tab a row of its model worded by the row template text=, and a
label of the picked row. Its Lua half is rowtabs.moy/main.lua, its compiled
half rowtabs_wasm.moy."""
import uitree as ui

s = ui.state(objs=ui.model(key="k", k="", name=""), obj=ui.row_of("objs"), said="")


def opened():
    s.objs = [{"k": "0", "name": "Stage"}, {"k": "1", "name": "player"}, {"k": "2", "name": "coin"}]


def chose():
    s.said = "On " + s.obj


ui.hook("opened", opened)
ui.hook("chose", chose)


def build():
    with ui.page("Tabs"):
        ui.tabs("obj", text="{.name}", on="chose")
        ui.label("{said}")
