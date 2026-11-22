"""Settings -> LAST CRASH (#224 sprint 2): the kernel's last crash record,
readable on the console. The row exists only where the kernel keeps a record
(its binding is importable), shows the record's kind, and opens a read-only
panel with the record's lines; every other tier keeps its rows and pixels."""

from runtime import host_app, settings_layer
from runtime.crash_guard import crash_lines
from ui_said import said as saying
from ws_helpers import build_ws

DT = 1 / 30
REC = {"kind": "task_wdt", "task": "mp_task", "id": "kernel-test", "role": "app",
       "what": "console hung: no frame in 15s", "reset": "task_wdt",
       "pc": 0x4200ABCD, "cause": 0, "addr": 0, "boot": 12, "uptime_ms": 3456}


def _kernel(monkeypatch, rec):
    import settings_ui
    monkeypatch.setattr(settings_layer, "crash_available", lambda: True)
    monkeypatch.setattr(settings_layer, "last_crash", lambda: rec)
    monkeypatch.setattr(settings_ui, "last_crash", lambda: rec)


def _dump(monkeypatch, size, clear):
    import settings_ui
    monkeypatch.setattr(settings_layer, "core_dump", size)
    monkeypatch.setattr(settings_ui, "core_dump", size)
    monkeypatch.setattr(settings_ui, "clear_core_dump", clear)


def _said(drv):
    with saying() as got:
        drv.frame(DT)
    return [e[1] for e in got if e[0] in ("label", "button")]


def _open(tmp_path):
    ws = build_ws(tmp_path)
    drv = host_app.ConsoleDriver(ws)
    ws.open_settings()
    drv.frame(DT)
    return ws, drv


def test_no_kernel_no_row(tmp_path):
    ws = build_ws(tmp_path)
    assert "crash" not in [r[0] for r in ws.settings_layer._settings_rows()]


def test_the_row_opens_a_panel_that_a_press_closes(tmp_path, monkeypatch):
    _kernel(monkeypatch, REC)
    ws, drv = _open(tmp_path)
    sl = ws.settings_layer
    rows = sl._settings_rows()
    assert ("crash", "LAST CRASH", "crash") in rows
    sl.set_msel = [r[0] for r in rows].index("crash")
    sl.settings_adjust(1)
    assert sl.showing("crash") is True
    drv.frame(DT)                       # the panel draws without raising
    ws.input.begin_frame()
    sl.close_page()
    assert sl.showing("crash") is False
    drv.frame(DT)


def test_the_row_with_no_record_reads_none(tmp_path, monkeypatch):
    _kernel(monkeypatch, None)
    ws, drv = _open(tmp_path)
    ws.settings_layer.set_msel = [r[0] for r in ws.settings_layer._settings_rows()].index("crash")
    ws.settings_layer.open_page("crash")
    assert _said(drv) == ["NO CRASH RECORDED", "Back"]


def test_the_panel_lines_name_what_stopped_and_what_ran():
    lines = crash_lines(REC)
    assert lines[0] == "TASK_WDT IN MP_TASK"
    assert lines[1] == "APP kernel-test"
    assert "PC 4200ABCD  CAUSE 0" in lines
    assert lines[-1] == "CONSOLE HUNG: NO FRAME IN 15S"
    assert crash_lines(dict(REC, id=None))[1] == "NO APP OPEN"


def test_a_core_dump_in_flash_is_on_the_page_and_the_row_without_a_record(
        tmp_path, monkeypatch):
    _kernel(monkeypatch, None)
    _dump(monkeypatch, lambda: 40960, lambda: True)
    ws, drv = _open(tmp_path)
    sl = ws.settings_layer
    assert sl.crash_word() == "Dump"
    sl.open_page("crash")
    said = _said(drv)                   # the dump's line and its button draw
    assert said[-3:] == ["CORE DUMP 40 KB IN FLASH", "Clear core dump", "Back"], said


def test_the_page_clears_the_dump_on_its_button(tmp_path, monkeypatch):
    _kernel(monkeypatch, REC)
    size = [40960]

    def clear():
        size[0] = None
        return True
    _dump(monkeypatch, lambda: size[0], clear)
    ws, drv = _open(tmp_path)
    ws.settings_layer.open_page("crash")
    drv.frame(DT)
    drv.press("a")                      # the page's first button: Clear core dump
    drv.frame(DT)
    assert size[0] is None
    assert ws.settings_layer.showing("crash") is True
    assert "Clear core dump" not in _said(drv)
    drv.press("a")                      # Back, the page's one button left
    drv.frame(DT)
    assert ws.settings_layer.showing("crash") is False
