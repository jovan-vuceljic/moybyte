# A Python app from docs/app_api_v1.md alone (sections 1, 3, 5): a list
# longer than the screen, which the engine scrolls, and the row last
# picked kept in prefs across runs. tests/test_app_examples.py drives it.
s = ui.state(items=ui.model(key="name", name=""), cur=ui.row_of("items"))
ui.app("Shopping", icon="list")


def opened():
    s.items = [{"name": "Item %d" % n} for n in range(1, 41)]
    s.cur = prefs.get("cur") or "Item 1"    # saved across runs and reboots


def pick(row):
    prefs.set("cur", row.name)


ui.hook("opened", opened)
ui.action("pick", "Pick", pick, takes="row")


def build():
    with ui.page("Shopping"):
        with ui.rows("items", cur="cur"):
            ui.link("pick", label="{.name}")
