-- Conformance fixture `pictures` (level 2), the Lua half: a seg of
-- look="pictures" over an enum, each value's word an image's text (no picture
-- put: the engine's plates alone), and a label of its value. Its Python half
-- is ../app.py.
ui.app("Pictures", { icon = "image" })
local s = ui.state { face = ui.enum("x", "y", "z", { init = "x" }) }
ui.labels("FACES", { x = "own:face:x", y = "own:face:y", z = "own:face:z" })

ui.page("pictures", function()
  ui.seg("face", { label = "Face", labels = "FACES", look = "pictures" })
  ui.label("Face {face}")
end, { title = "Pictures" })
