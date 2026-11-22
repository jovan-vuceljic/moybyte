"""A page whose hints band leads with its status words (status=)."""
import uitree as ui

s = ui.state(word="View only", n=0)


def go():
    s.n += 1


ui.action("go", "Go", go, keys=("g",))


def build():
    with ui.page("Band", status="{word}"):
        ui.label("{n}")


def layer(engine):
    import uitree_app
    return uitree_app.app_layer("band_status_c", "Band", build, engine=engine)
