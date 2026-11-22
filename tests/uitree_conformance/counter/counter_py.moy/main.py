# Conformance fixture `counter` (level 1), the Python cart: ../app.py as a
# cart, its `ui` the UI tree API (the moybyte.uitree extension) and its root
# page `build`.
s = ui.state(count=0, loud=False)
ui.app("Counter", icon="calc")


def add():
    s.count += 1


def reset():
    s.count = 0


ui.action("add", "Add one", add)
ui.action("reset", "Reset", reset, when="count", off="grey")


def build():
    with ui.page("Counter"):
        with ui.group("Count"):
            ui.info("Count", "{count}")
            ui.toggle("Loud", "loud")
            ui.link("add")
            ui.link("reset")
            ui.label("{count|plural press,presses} so far, {loud?loud:quiet}")
