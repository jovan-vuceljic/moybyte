-- A form in the UI tree API, which the boards' suites run on the C engine:
-- a page of rows, a field and an action, whose presses pmem cell 0 keeps.
ui.app("Form", { icon = "calc" })
local s = ui.state { name = "moy", wifi = true, count = 0 }

ui.action("add", "Add one", function()
  s.count = s.count + 1
  pmem(0, s.count)
end, { hint = "Add" })

ui.page("form", function()
  ui.field("name", { label = "Name", max = 12 })
  ui.toggle("wifi", { label = "Wi-Fi" })
  ui.info("Presses", { value = "{count}" })
  ui.button("add", { focus = true })
  ui.label("{name}, Wi-Fi {wifi?on:off}")
end, { title = "Form" })
