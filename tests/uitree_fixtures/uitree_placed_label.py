"""A placed page's labels in rows: a size="text" label beside a dim one,
the same with face="ui" (the face size="text" is measured in), and an
icon with no words beside the same with no icon, both dim."""
import uitree as ui

s = ui.state(t="Sound effects for the long level", st="12 notes")


def build():
    with ui.page("Labels"):
        with ui.row("a"):
            ui.label("{t}", size="text")
            ui.label("{st}", tone="dim")
        with ui.row("b"):
            ui.label("{t}", size="text", face="ui")
            ui.label("{st}", tone="dim")
        with ui.row("c"):
            ui.label("", icon="music", tone="dim")
        with ui.row("d"):
            ui.label("", tone="dim")


def layer(engine):
    import uitree_app
    return uitree_app.app_layer("placed_label", "Placed label fixture", build, engine=engine)
