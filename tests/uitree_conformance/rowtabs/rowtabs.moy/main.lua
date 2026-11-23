-- Conformance fixture `rowtabs` (level 2), the Lua half: tabs over a row_of, a
-- tab a row of its model worded by the row template text=, and a label of the
-- picked row. Its Python half is ../app.py.
ui.app("Tabs", { icon = "list" })
local s = ui.state { objs = ui.model { key = "k", k = "", name = "" }, obj = ui.row_of("objs"), said = "" }

ui.hook("opened", function()
  s.objs:set({ { k = "0", name = "Stage" }, { k = "1", name = "player" }, { k = "2", name = "coin" } })
end)
ui.hook("chose", function() s.said = "On " .. s.obj.k end)

ui.page("rowtabs", function()
  ui.tabs("obj", { text = "{.name}", on = "chose" })
  ui.label("{said}")
end, { title = "Tabs" })
