"""Conformance fixture `pictures` (level 2), the Python half: a seg of
look="pictures" over an enum, each value's word an image's text (no
picture put: the engine's plates alone), and a label of its value. Its Lua
half is pictures.moy/main.lua, its compiled half pictures_wasm.moy."""
import uitree as ui

s = ui.state(face=ui.enum("x", "y", "z", init="x"))
ui.labels("FACES", {"x": "own:face:x", "y": "own:face:y", "z": "own:face:z"})


def build():
    with ui.page("Pictures"):
        ui.seg("Face", "face", labels="FACES", look="pictures")
        ui.label("Face {face}")
