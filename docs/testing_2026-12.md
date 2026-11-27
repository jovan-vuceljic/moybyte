# Testing, 2026-12: one full, fast board suite, and the logic on the host

A plan for the testing framework, for the work after the next release. It
says what each board check becomes, how one suite runs on every board, how
performance becomes a test, and the order of the work. Measured numbers are
in the appendices, each table saying when and where it was taken; the body
points at them.

## 1. The owner's direction (2026-11-27)

- **One board suite, full and fast.** "I'd rather have a FULL FAST suite
  than different ones." There are no quick or full tiers and no smoke
  subsets. The pass runs the whole suite on every board, every time.
- **Logic moves to the host.** A shell flow, a menu, a layout, the Editor
  or a settings walk is a host test, where the pixel goldens and the input
  tests already run on every push. A board keeps what needs the hardware:
  panel and flush, input devices, audio, card and store, Wi-Fi and radio,
  OTA, boot, memory on the real allocator, timing, each cart tier really
  running (Python, Lua, compiled), and a match between two boards.
- **Performance is tested on the boards** ("we need performance tests on
  the boards"), in the same suite, with a bound per board that fails the
  pass.
- **One performance protocol.** "It shouldn't matter, our OS should be
  written in such a way that its performance doesn't degrade over time." A
  board's numbers at the end of the suite must match its numbers at the
  start. A difference past the noise band is a bug and a failing test, not
  a second protocol. This replaces the 2026-11-15 rule ("fresh boot or
  after the suite, never mixed") when phase P4 lands.
- The work starts after the next release.

## 2. What needs a board

A check stays on a board when it needs one of these:

1. **The cross-compiled C on the chip**: the Xtensa and RISC-V builds, the
   PPA and 2D-DMA, a P4's U-mode and PMP.
2. **A peripheral**: the panel and its flush, touch, keys, pad, audio,
   card, LoRa, LEDs, battery, clock chip, GPIO.
3. **The radio**: Wi-Fi, BLE, ESP-NOW, NTP, the live socket, SSH.
4. **Flash and the store on real media**: commits under a running cart, a
   power-cycle persistence, a full store.
5. **The real allocator**: internal SRAM, PSRAM, fragmentation, the gc
   heap's areas, low-water.
6. **Time on the real clock**: fps, frame ms, budgets, watchdogs.
7. **The boot and OTA chain**: the logo before the VM, partitions,
   rollback, signatures under the image's key.
8. **A match** between two real radios.

"It runs on MicroPython" is not on the list. The host builds the desktop
MicroPython with the native usermods (`tools/preflight.sh`'s lane) and
already runs device code on it (`tests/test_uitree_micropython.py`,
`tests/test_p8_micropython.py`). "It is the device tier's Python" is not on
the list either: the host executes the device tier
(`.claude/rules/testing.md`).

Appendix B is the inventory: every on-glass test, what it checks, whether
it needs the board, the host test that covers it, its measured cost and
its verdict. The verdicts fall into four kinds:

- **KEEP.** It stays and moves into the one suite.
- **FOLD.** It stays but merges into another check: the same cart launch,
  the same measurement, or one batch.
- **HOST.** It goes; a named host test holds it (`HOST+` means the plan
  writes that host test first).
- **DUP.** It is the same body under another name, and goes.

What the inventory found, in short:

- **Shell logic costs the boards little time.** The settings, projects,
  appearance, claims, parking, chrome and retained-surface tests take about
  a second each (Appendix A3). Moving them is about where logic belongs,
  not about speed. Two exceptions are slow: the pause menu (FOLD: its dim
  goes to the host, its heap half stays) and the wifi-widget test.
- **The compiled tier is half of every console suite** (Appendix A2). Its
  checks need the board: they are the tier really running, its traps, its
  signatures and its memory. The cost is in how they are set up, not in
  what they check (section 3).
- **The roster files leave holes.** Appendix B marks the coverage gaps:
  - The CoreS3 runs none of the compiled tier, though its board.toml takes
    `moy_wasm` and `moy_elf`.
  - The Guition S3 has no Paint save, no wifi widget and no compiled-app
    checks.
  - The T-Deck and Guition S3 have no timed lanes and no deep-recursion trap.
  - Doom-sized pushes run on two boards only.
  - The `the_panel_is_…` / `the_system_canvas_is_…` checks are four copies
    under four names.

  These holes are what per-board roster files produce. They are the
  argument for section 4.

## 3. Where the time goes

Appendix A1 has each board's suite and perf stage, and the walls of whole
passes. Appendix A3 has the top 20 tests on the T-Deck, the Guition P4 and
the C3 Zero, the boards with per-test times on disk (the other boards' junit
files were not kept: see section 8).

### The shape of a pass

- **The Zeros run after the T-Deck's row, one at a time**
  (`tools/board_pass.py`, so the page can play its match against the
  T-Deck). A pass with all boards is therefore the T-Deck's suite, then the
  XIAO's, then the C3's, end to end (`zero_suite` waits on the T-Deck's
  row and holds one lock for both Zeros). That chain is longer than any
  console's suite, and every pass wall in A1 is bounded by the C3's suite.
- **The perf stage runs one board at a time**, because two consoles in one
  two-player cart form a match. `tools/radio_room.py` already serialises
  every run of a multiplayer cart, the perf stage's included, so the
  stage-wide serialisation is a second lock over the same hazard.

### The consoles (T-Deck, Guition P4 measured; the others share the bodies)

| cause | where | speedup |
|---|---|---|
| **S1** 20 VM soft resets | `soft_resets_leave_psram_flat(n=20)`: the slowest test on every console | A per-cycle leak shows at cycle 3, because the baseline is cycle 2. Take n=6. The suite-wide drift test (section 5) covers slow leaks |
| **S2** each compiled-fixture test builds, signs, pushes and rescans its own variant | `_wasm_fixture_variant`, `_push_one_shot`, `wasm_carts_push`, `jet_push`, `stuck_carts_push`, `lanes_carts_push`, `tree_form_push`, `wasm_app_push`, `_deep_init_push`, `wasm_files_push` | Build every fixture for the chip once per session (cached by content hash under `.build/`). Push them all in one `recv` session, then rescan once. This matters most on the UART P4s, whose console runs at 115200 between pushes |
| **S3** fixed waits | the shared bodies call `board.drain(s)` with constant seconds well over a hundred times (one 16 s, one 9 s, a dozen 2.5 s), plus `time.sleep` | Wait for the line that ends the state (`REMOTE run`, the Player's `cart_error`, the `STOP`/`KSTOP` lines, `state`'s stack) with the constant as the ceiling. This is the rule the testing rules already give for `drag done` |
| **S4** Jet Teapot runs three times a pass | full width, half width (the floors), and the perf stage | One uncapped run at full width is the perf metric (section 5). The half-width run keeps a short window as a config check |
| **S5** conformance corpora make one serial round trip per case | `theme_custom_matches_host`, `picker_kernel_matches_sspr`, `shift_last_matches_the_reference`, `fonts_match_host`, `sprites_match_host` | Run the corpus on the board in one `py --exec`. It returns one CRC per case, compared on the host in one reply |
| **S6** each launch and leave is a full launcher round trip | `cart_runs_and_exits`, `_notice_on_launch`, `_runs_clean`, `leave_cart` | Group the checks that need the same cart into one launch, and measure the cart's fps while it is up (section 5) |
| **S7** network fetches from the internet | `pkg_installs_a_cart_from_the_carts_repo` | Point the pkg source at the bench mirror the Zero suite already serves, and keep one test that names the real index |

### The C3 Zero's hour (and the XIAO's 21 minutes)

| cause | where | speedup |
|---|---|---|
| **Z1** a 12-minute soak, by design | `test_zy_a_session_soak_keeps_the_board_s_ram`, `SOAK_S` | Folded into the suite-wide drift test (section 5). A suite of about 25 page sessions is the soak, with the heap read before and after each test |
| **Z2** a hard reset, a boot and a Wi-Fi join every time the suite needs the REPL | `Zero.repl()` ends in `restart()`. About 22 call sites, and `_heap` is one of them | `Zero.look()` and `Zero.peek()` read the same heaps with the host's loop stopped and taken up again, with no reset. Every heap read moves to them, and `restart()` stays only in tests about a reset |
| **Z3** a fresh headless Chrome, empty profile, sign-in and console boot per scenario | `_browse` → `browsershot.mjs`, one process per call | One Chrome per module, driven over CDP across scenarios. The paired profile is kept (as `profile=` already allows), and the console stays booted and is reused. A scenario that is about a fresh browser (displacement, a second browser, a reconnect) opens a new tab or profile on purpose |
| **Z4** tests that each reboot for the same reason | pmem after a reboot; an imported cart and a setting surviving a reset; the page reconnecting after a reboot | One reboot, three assertions |

Every page scenario costs minutes on both Zeros alike (A3). The XIAO has
PSRAM and the C3 has none, so the board's CPU is not the main cost. Which
step inside a scenario takes the time (Chrome's start, the pack's first
fetch and compile, the sign-in wait, a `waitFor` that runs to its ceiling)
is not measured. Phase P0 measures it before Z3 is built.

### Parallel boards

Every board, the Zeros included, runs its suite from the first minute,
concurrently. The things that need two boards (the Zero's page against a
console, and a match between two consoles) run as one **pair stage**
after both boards' suites end. Multiplayer carts stay under
`tools/radio_room.py`'s lock. Nothing else serialises.

## 4. One suite, every board

### Layout

- One package, `+tests/glass/conftest.py` and area modules beside it:
  `boot`, `panel`, `input`, `memory`, `store`, `radio`, `ota`, `services`,
  `carts` (the Python and Lua runs, with their perf), `compiled`,
  `conformance`, `web` (the browser console, live socket and SSH: the
  Zeros' tests and the consoles' web console), `perf` (the probes and the
  drift test) and `pair`.
- The bodies in `tests/on_glass.py` move into those modules. A check is
  written once, where it runs. There is no body file beside a call file.
- The per-board files (`tests/test_tdeck_on_glass.py`,
  `tests/test_guition_on_glass.py`, `tests/test_cores3_on_glass.py`,
  `tests/test_p4_on_glass.py`, `tests/test_guition_p4_on_glass.py`,
  `tests/test_elecrow_p4_on_glass.py`, `tests/test_zero_on_glass.py`) go.
- The session names its board by id (`MOYBYTE_GLASS_BOARD=tdeck`, the
  `[board] ota` id) and port. The pass sets both.
- Module order is declared in the conftest, not left alphabetical. The
  session shares one board in that order: boot first, then perf's start
  probe, and the drift probe last.

### Capabilities come from board.toml, not from a roster

`+tools/board_caps.py` (or a function in `tools/board_config.py`, beside
`roster_only`) derives each board's capability set from what the board
already declares:

- `[board] tier`: `handheld`, `desktop`, or no tier for the headless Zeros.
  This selects windowed or fullscreen checks.
- `[board] chip`: `esp32s3`, `esp32p4`, `esp32c3`. This selects chip
  checks: U-mode, PPA, 2D-DMA.
- `[native.shared]` takes and denies: `moy_wasm`, `moy_elf`, `moy_sd`,
  `moy_usbdisk`, `moy_play`, the Lua tier and so on.
- `[[hardware.resource]]` names: `radio`, `speaker`, `mic`, `bar`,
  `battery`, `backlight`, `lora`, the card on its SPI row, the `gpio`
  lease row, `usb`.
- `[web] console` and `[roster]` (the Zeros' checks already skip on these).
- `[serial] attach_only`.

A test declares what it needs, `@needs("wasm", "sd")`, and the conftest
skips it with the reason "board.toml declares no `sd`".

- A tier difference stays an ARGUMENT to the body (`door=`, `windowed=`),
  as `.claude/rules/testing.md` already says. It is now read from the
  capability set instead of being passed by a per-board call.
- A lever a board lacks is ABSENCE (`docs/board_ports_2026-08.md`): the
  skip says so, and a check never passes vacuously.

### A board's own hardware

Most of the CoreS3's 13 own tests (and the T-Deck's, Guition S3's and
Guition P4's few) are a generic check over a resource kind: a battery reads
in range, a backlight steps, an RTC keeps time and takes NTP, a mic's
samples are not flat, an amplifier answers and stays at volume 0, an LED bar
takes a frame and goes dark, a touch controller and a pad answer on their
IRQ, the panel is its declared geometry.

- **Generic checks.** The `[[hardware.resource]]` row gains a `check`
  naming the generic check and the facts it needs (the driver, a voltage
  range, an id). Every board with that resource runs it. The T-Deck gets
  the battery check the day its row says `check`.
- **Truly board-own checks.** What has no generic shape (the T-Deck's
  letter keys from the matrix and its mic field, the Guition P4's GSL3680
  and PPA, the Guition S3's failed-flush recovery) goes in
  `+tests/glass/boards/`, one module per board id. The suite imports it
  only when that board runs. Nothing else lives there.
- **A host guard.** `+tests/test_board_caps.py` checks that every
  `[[hardware.resource]]` row has a `check` or a declared `check = "none"`
  with its why. It also checks that every `@needs` name is a capability
  some board.toml can declare (a typo is a failure, not a silent skip),
  and that each board's set is what its toml says.

### A new board on day one

When its board.toml lands, the board has a capability set. The pass finds
it by its `[board] ota` id, with no suite file to write. It runs every
shared check its capabilities admit. A resource without a check fails
`+tests/test_board_caps.py`, so the porter writes the check or declares
none. `tests/test_board_pass.py` stops pinning one suite per console board
and pins instead that every board.toml is a pass target with a capability
set.

### The session

- **One reboot at the start, on every board.** The attach-only boards are
  rebooted through esptool, as `tools/board.py X reboot` does. This gives
  every board the same starting state, which perf's start probe needs.
  It also removes the dirty-desk failures the testing rules warn about. It
  costs one boot, about ten seconds (A1's boot lane).
- **The store is given back** when the session closes, as today.
- **The board is left at its launcher at volume 0**, as today.

### How it fits `tools/board.py pass`

- The pass builds, flashes and boots as today, then runs `pytest
  tests/glass` per board, all boards concurrently, the Zeros included.
- The pair stage follows when its two boards are in the pass.
- **There is no perf stage**: the measurements are tests in the suite
  (section 5), and the record is written from them.
- `-k` stays, for a developer's iteration. A run filtered by `-k` is marked
  partial in the table and writes no ledger record.
- `--no-perf` goes. The suite is one.
- `perf-baseline` becomes "the start probe alone, on the board as it is",
  for an A/B by hand.

## 5. Performance as tests

### Which numbers become tests

| metric | boards | bound | where it is measured |
|---|---|---|---|
| desk idle drawn fps | consoles | exactly 0: an idle desk draws nothing, and every record on every board reads 0 (A4) | start probe, end probe |
| desk idle gc collections, longest pause | consoles | 0 collections at idle (every record reads 0); the pause is reported | start and end probes |
| desk idle loop ms | consoles | history band | start and end probes |
| internal SRAM free, largest block, low-water; PSRAM free, largest; gc held and live after a collect | every board | history band at the start probe; drift band at the end (below) | start and end probes |
| the roster's drawn fps and frame ms | consoles | history band | in the test that runs the cart. Star Catcher, Sakura Lua and Brick Siege Lua already run (`cart_runs_and_exits`, the front-run checks); Brick Siege and Letter Blitz get one launch each |
| window drag fps and frame ms | windowed tier | history band | the drag test, which also holds `a_drag_touches_no_storage_and_rebuilds_no_cache` and the `wm` meters |
| Jet Teapot uncapped fps and frame ms | `moy_wasm` | history band; it replaces `JET_*_FPS_FLOOR` | the one Jet run (S4) |
| hello and blit fps, Doom fps | `moy_wasm` | history band; it replaces `WASM_*_FPS_FLOOR` and `DOOM_FPS_FLOOR` | the existing runs |
| match ticks per second, stall | pair stage | absolute bounds from `docs/netplay_v1.md` §3's lock meters (`lock=late/stall/…`), set when the stage lands | pair stage |
| Zero: internal free idle and live, largest, live-socket rtt, page root, reload boot, Improv join, claim to live | Zeros | history band. The rtt's p90 is too noisy for a band (A4) and keeps the absolute bound the suite has (power save cannot pass) | already in their suite |

**The bound rule.**

- **The baseline** is the median of the board's last ten records under the
  one protocol, at commits other than the one under test, from
  `~/.cache/moybyte-perf/<board>.jsonl`.
- **The band** is the largest of:
  - the unit's floor (`DEFAULT_BAND` in `tools/perf_pass.py`: 5% for fps
    and KiB, 10% for ms);
  - four times the relative median absolute deviation of those ten values;
  - three times the run's own within-run deviation.

  `MIN_MOVE` stays as the absolute floor.
- **The gc heap's held size is discrete** (it moves in whole areas). Its
  bound is the history's mode, not a percentage.
- **A metric worse than its band is measured once more, in the same run.**
  The test fails only when both readings are past the band.

The history justifies the re-measure (A5). With these bands, about one
metric reading in 75 would have been past the band over 2026-11-15..27.
Most of those were steps that stayed in later runs, which are real changes
(the Guition P4's window drag on 2026-11-22 is one). A few were one-off
readings just past the 5% floor, and the second reading absorbs those.

**A change that is meant to move a number** is accepted by
`+tools/perf_accept.py BOARD METRIC --why "#N"`. It appends an `accept`
record, and the baseline restarts from the runs after it. An accepted move
is a decision with an issue, not a band widened by hand.

**Warming.** A board with fewer than five records under the protocol
reports its numbers and gates nothing. A new board gates from its sixth
pass.

### Window lengths, from the noise

A4 holds the noise statistics behind these choices:

- **Capped carts.** A cart held at its cap moves less than 1% between
  2-second windows inside a run, and about 2% at most between runs. The
  stage takes a 4-second settle and three 2-second windows, which leaves a
  margin of five to ten times under the 5% floor. Two windows after a
  2-second settle keep the median stable.
- **Frame ms.** It needs PERF DIAG, and PERF comes once a period. Two PERF
  samples stay.
- **Jet uncapped.** Its frame ms varies 7–8% between samples within a run,
  but the median of five varies under 1% between runs. Five samples stay.

So a roster cart costs about 10 seconds of measuring instead of about 18
(the stage's phases, A4), and it rides a launch the suite already makes.

### The drift test: start against end

- **`test_perf_start_probe`** runs first after the session's reboot. It
  takes the probe set:
  - the heaps after a collect: internal free, largest and low-water; PSRAM
    free and largest; gc held and live;
  - the desk idle (drawn fps, collections, loop ms);
  - one capped cart's fps and frame ms (Star Catcher: the lowest within-run
    noise of the roster on every board);
  - Jet's uncapped fps where the board takes `moy_wasm`.

  Fragmentation is the largest block against free. Low-water only falls,
  so its check is a floor (what a Wi-Fi and BLE start needs, from the
  board's existing radio checks), not a drift.
- **`test_perf_drift`** runs last and takes the same set. Each metric must
  be within its band of the start. On the Zeros the probe is `Zero.look()`
  with no reset, taken before and after every test. That gives a heap trace
  across the whole suite, which is the soak's question answered by the
  suite itself (Z1).
- **What it costs.** About 25 seconds a probe on a console, so under a
  minute a suite. The roster's numbers come from tests that already run.

**What the first runs will show** (A6, the five commits where a board has
both a fresh and an after-suite record):

- **Frame rates do not drift.** Every fps and frame ms is within its band
  but one: Letter Blitz's frame on the T-Deck, +11% at one commit (+6% at
  another, inside the band).
- **Memory drifts on every console, at every commit compared.**
  - Internal SRAM free falls by a tenth to over a third.
  - Its largest block falls by up to two thirds.
  - PSRAM free falls by up to a fifth.
  - The gc heap holds one area more (1 → 1.5 MB on the S3s).

The known sources this test names:

- **#248.** The gc heap grows by doubling and never gives an area back.
  That is the gc-held step.
- **The internal largest block halving after a suite** on all four
  consoles compared. The CoreS3, which has no fresh record, shows the same
  block as its noisiest heap metric between runs (A4).
- **#249.** A cart measures behind the carts run before it.
- **#276.** The C3's internal RAM under an SSH session.
- **The Guition P4's popover close**, slower after a fresh boot than deep
  in a session (#248's first item). This is drift in the other direction,
  and the probe catches it once the popover close is in the probe set.

**How the plan handles the expected failures.** The drift test lands in P4
with every memory metric marked `xfail(strict=True)`, each naming its
issue: #248 for gc held, and the internal-SRAM fragmentation, which P4
files as its own issue through the `issues` skill. The fps and ms metrics
assert from the first day. Strict means a fix turns the mark into a
failure, so the mark goes with the fix. Each finding is classified in its
issue:

- **A leak.** Fix it.
- **A cost paid at first use and kept on purpose.** Move it to boot, so
  the start probe sees it too.

Both make "start equals end" true without a second protocol.

### The ledger, one protocol

- **Records.** They carry `protocol: {"start": "pass"}`. The start probe's
  heap and desk numbers, the in-suite cart numbers, and a `drift` block
  (end minus start for each probe metric) make one record a pass.
- **The old records.** The `after-suite` and `fresh` records stay in the
  history files and compare with nothing. The baseline restarts with the
  first `pass` record, and warming covers the gap.
- **`tools/perf_ledger.py`** loses `--protocol`. The ledger's header says
  the one protocol and that the drift test holds start equal to end.
- **What P4 corrects** when it lands. Each of these carries the
  two-protocol rule or the separate stage:
  - CLAUDE.md's numbers table (the "fresh boot or after the suite, never
    mixed" row);
  - `.claude/skills/perf/SKILL.md` (the pass paragraph and the protocol);
  - `.claude/skills/on-glass/SKILL.md` (the perf stage, `perf-baseline`,
    the per-board suite list);
  - the header of `docs/perf/ledger.md`, through its generator;
  - `tools/perf_pass.py` (THE PROTOCOL, THE COMPARISON);
  - `tools/board_pass.py` (THE PERF STAGE, one board at a time);
  - `tools/board.py`'s `perf-baseline` help;
  - `tests/test_perf_pass.py`, `tests/test_perf_ledger.py` and
    `tests/test_board_pass.py`.
- **What P2 corrects** for the per-board suite files:
  - `.claude/rules/testing.md` (the on-glass paragraph and its list of
    files and variables);
  - the board READMEs that name their suite file;
  - the new-board steps in `docs/board_ports_2026-08.md`;
  - `runtime/README.md` and `.claude/rules/shell.md`.

  A grep for the words on_glass.py and after-suite is the list.

## 6. The host side

### What moves there

Appendix B marks each move. Most have a host test already:

- **Claims and seeding:** `tests/test_device_seed_parity.py` and
  `tests/test_app_registry.py`.
- **The windowed desk:** `tests/test_wm_windowed.py`,
  `tests/test_wm_content_freeze.py` and `tests/test_surface_model.py`.
- **Card verbs and pointer gestures:** `tests/test_home_card_verbs.py`
  and `tests/test_kinetic_scroll.py`.
- **Settings and the shell's apps:** `tests/test_settings_scroll.py`,
  `tests/test_desktop_shell.py` and `tests/test_projects_list.py`.
- **The pause menu and the top bar:** `tests/test_modal_scrim.py` and
  `tests/test_top_bar.py`.
- **Input hints, the dev channel and services:** `tests/test_input_hint.py`,
  `tests/test_dev_channel.py`, `tests/test_aio.py` and
  `tests/test_restart_policy.py`.
- **Cart levels and modules:** `tests/test_api_level.py` and
  `tests/test_wasm_cart.py`.

### The gaps the moves expose (P1 writes these first)

- A settings list let go mid-swipe does not snap back to the top (the
  board's `scroll_survives_release`). Check `tests/test_settings_scroll.py`;
  write it if absent.
- The bar's wifi widget opens Settings' WIFI panel as a popover hung from
  the widget, on both tiers (`tests/test_top_bar.py`).
- The CoreS3's hints name the pad's keys (`tests/test_input_hint.py` with
  the CoreS3's board keys).
- A module built for another chip, a stale-format module and no module at
  all each choose the interpreter: the file-choice half. The run on the
  interpreter stays on the board, once.
- An asyncio service and an on-crash restart under the desktop MicroPython,
  not only CPython (`tests/test_aio.py`, `tests/test_restart_policy.py`).
- The font set an image stages for its tier (`the_font_set_is_the_tiers`),
  read from the staging rather than the board.

### Host slow spots (A7, CI's 2026-11-27 run on dev)

- `test_frame_alloc.py` builds its compiled cart in a fixture setup, every
  run. Cache it by content hash under `.build/`, as the board fixtures will
  be (S2).
- `test_board_ports.py::test_a_rejected_chunk_names_the_chunk` takes
  exactly a minute. That is a timeout running out, not work: give the
  refusal a line to wait for.
- `test_moy_ssh.py`'s two slow-reader tests: shorten the reader's pacing
  so it is still slower than the writer.
- The unix-MicroPython builds in session setups (`test_uitree_c_memory.py`,
  `test_uitree_c_micropython.py`): one session build, shared.
- P1 runs the host suite once with `--durations=0` and folds what a
  duration list shows.

### CI serial against local xdist

CI runs the host suite in four shards per Python version, serially inside
each shard (`.github/workflows/ci.yml`, `tools/ci_shard.py`). Preflight runs
it under xdist (`-n auto`). The two schedulers are how a timing pin passed
in one and failed in the other. The plan:

- The shards run under xdist too (`-p xdist -n auto`), so both places
  schedule alike.
- A test that needs wall-clock quiet declares a `serial` mark. Preflight
  and CI run those alone after the rest, as CI already does for
  `tests/test_redraw_on_change.py`.
- A pin on time becomes a pin on a count wherever a counter exists, as the
  frame counters already allow.
- CI's second Python version (3.10 beside the CI image's 3.11) doubles
  CI's work. Whether a host tool user still needs 3.10 is the owner's call;
  the plan does not depend on it.

## 7. Targets and the order of work

### Targets

A suite's time below includes its perf and drift tests and excludes build,
flash and boot.

| board | target |
|---|---|
| T-Deck, Guition S3 | 9 min |
| CoreS3 | 8 min (it grows: it gains the compiled tier and every shared check its board.toml admits) |
| Guition P4, Waveshare P4 | 10–11 min |
| Elecrow P4 | 12 min |
| XIAO Zero | 8 min |
| C3 Zero | 15 min |
| **a pass of every board** | **25 min wall**: build, flash, boot, the longest suite (the C3), the pair stage |

Appendix A1 has today's numbers beside these. How the consoles get there:

- S1 saves over a minute.
- S2 is expected to save the most, an estimate of a fifth of the compiled
  tier's minutes (P0's per-test history checks it). The tier is half of
  each suite.
- S3 to S6 save a minute or two each.
- The separate perf stage goes, and its numbers ride launches the suite
  already makes.

How the Zeros get there:

- Z1 removes the soak.
- Z2 and Z3 together remove most of each page scenario's fixed cost. The
  size of that cost is P0's first measurement.

The pass's wall falls most from running the Zeros concurrently instead of
after the T-Deck's row.

### Phases

Each phase lands alone and keeps coverage.

**The guard for every phase is the test-name map.**

- **The snapshot.** `+tests/glass_map.json` is written once, in P0, by a
  script that reads today's suite files with `ast`. It holds every (old
  test id, board) pair, and it is never regenerated.
- **The targets.** Each phase fills in where each pair went:
  - `glass:<new id>`;
  - `host:<node id>`;
  - `dup:<new id>`;
  - `deleted:<why, owner, date>`.
- **The checks.** `+tests/test_glass_map.py`, a host test, fails when:
  - a pair has no target;
  - a `host:` node id does not collect;
  - a `glass:` test does not exist;
  - **its `@needs` are not met by the capabilities of every board that ran
    the old test.** A board's coverage cannot shrink without an entry
    saying so.

**P0. Instrument and freeze.**
- The name-map snapshot and its host test.
- The pass keeps each board's junit file in `~/.cache/moybyte/junit/`,
  so per-test times have a history beside `timings.csv`.
- The Zero suite logs each browsershot step's time, which splits Z3's cost.
- No test changes.

**P1. Host first.**
- Write the gap tests (section 6).
- Delete the board copies the inventory marks HOST and DUP.
- Fix the host slow spots, and run the CI shards under xdist.
- Map entries: `host:` and `dup:`.

**P2. Capabilities and the one suite.**
- `+tools/board_caps.py` and `+tests/test_board_caps.py`.
- The `tests/glass/` package, the bodies moved, the per-board files
  deleted.
- The pass runs `tests/glass` per board, the Zeros concurrently, and the
  pair stage holds the Zero-against-T-Deck match and atan2 checks.
- The `check` field on hardware rows, and the board-own modules.
- The map's `glass:` entries are checked against capabilities.
- **New checks will fail on boards that never ran them** (the CoreS3's
  compiled tier first). P2 lands with each such failure as
  `xfail(strict=True)` naming a filed issue, never as a skip.

**P3. Speed.**
- S1–S7 and Z1–Z4.
- The map does not change. Only time does.
- The pass's table flags a suite past its target time. It is a report, as
  `tools/timings.py`'s 1.25× flag is.

**P4. Performance in the suite, one protocol.**
- The start probe and the drift test (memory metrics xfail with their
  issues).
- The roster, drag, Jet and Zero numbers taken in their tests.
- The perf stage removed, the record and ledger changes made, and the docs
  of section 5 corrected.
- Bounds report and gate nothing while each board warms.

**P5. Performance gates.**
- After five `pass` records per board, the bands fail the pass.
- `+tools/perf_accept.py` lands with this phase.

**P6. The match.**
- A two-console pair stage: two consoles on one multiplayer cart, under the
  radio room, with the world check armed on both sides as the Zero's page
  match already does. It runs Python and Lua carts.
- It records ticks per second and the lock's stall, a report for five
  passes and then a gate.

## 8. Risks, and what was not measured

**Risks.**

- **Losing coverage while moving bodies.** The name map is the answer. Its
  weak point is the snapshot: a test added between P0 and P2 must be added
  to the snapshot by its own commit.
- **New coverage looks like breakage.** The CoreS3's first compiled-tier
  run, and the drift test's memory metrics, will fail on real bugs. Strict
  xfails with issues keep the pass green on what was green, without hiding
  the new failures.
- **A false perf gate is worse than no gate.** If a board's bands fail
  passes that measured nothing new, people stop trusting the pass. The
  re-measure, warming, the accept record and the per-metric MAD are the
  defence. If one metric keeps flapping on one board, it is demoted to a
  report by an accept record with an issue, never by widening the band in
  code.
- **Shorter perf windows** were justified from capped carts' within-run
  noise (A4). An uncapped cart or a new tier needs its own look before its
  windows shrink.
- **One reboot at the start** changes the attach-only boards' contract: the
  session no longer attaches to a board as it is. Somebody driving a board
  by hand loses that state. The pass already reflashes, so only a
  `--no-flash` run is affected.
- **Deleting the soaks** (the C3's twelve minutes, twenty resets down to
  six) trades a long-run leak detector for the suite-wide drift trace. A
  leak that needs hundreds of cycles to show would now pass. A long soak is a
  separate tool run by hand, not part of the pass (§9).
- **A shared Chrome page across Zero tests** couples them: a page left in a
  bad state fails the tests after it. Each test that needs a fresh page
  asks for one, and the fixture reloads after a failure.

**Not measured.**

- **Per-test times on the Waveshare P4, the Elecrow P4 and the Guition
  S3.** No junit file of a full suite was on disk: the pass directories of
  2026-11-26 and 27 kept build logs only for those boards. Their causes are
  inferred from the shared bodies they call and from the T-Deck and Guition
  P4. P0's junit history fixes this.
- **The split of a Zero page scenario's minutes** (Chrome's start, the
  pack's first load, sign-in, `waitFor` ceilings), and **the cost of one
  Zero hard reset with its Wi-Fi join**. The suite logs keep only each
  scenario's last 4,000 characters. P0 measures both before Z2 and Z3 are
  sized.
- **The host suite's full duration list.** Only CI's top 25 per shard was
  read (A7).
- **The drift of the Zeros and the CoreS3 against a fresh boot.** No fresh
  record exists for them (A6 covers the T-Deck, the Guition S3, the
  Waveshare P4 and the Guition P4).
- **The match's ticks and stall.** No pass records them today. The pair
  stage's bounds are set from its first records.

## 9. The owner's decisions (2026-11-27)

The owner took the plan as recommended:

1. **Perf is a gate.** From P5 each board's history band fails the pass,
   with a second reading before failing and an accept record for an
   intended move.
2. **The drift test lands before the drift is fixed.** The memory metrics
   land as strict xfails naming #248 and a fragmentation issue; fps and ms
   assert from the first day. The test is what shows the fix worked.
3. **The soaks go from the pass.** The C3's twelve-minute soak goes and the
   twenty soft resets become six; the suite-wide drift trace replaces them.
   A long soak, when wanted, is a separate tool run by hand.

---

## Appendix A. Measurements (2026-11-27, this bench)

These are a snapshot for this plan, not kept current. The live numbers are
in `~/.cache/moybyte/timings.csv` (`tools/timings.py`), the perf records in
`~/.cache/moybyte-perf/`, and `docs/perf/ledger.md`.

### A1. Suite and stage times

From `tools/timings.py --tool pass`: the median of the last ten passing
runs of each lane (fewer where marked), read 2026-11-27 17:20.

| board | suite | perf stage | flash | boot |
|---|---|---|---|---|
| tdeck | 16m42s | 2m24s | 47s | 8s |
| guition_s3 | 15m36s | 2m28s | 1m18s | 6s |
| cores3 | 55s (n=5) | 2m19s (n=5) | 45s | 6s |
| p4 | 22m10s | 2m54s | 57s | 10s |
| guition_p4 | 19m03s | 2m51s | 46s | 10s |
| elecrow_p4 | 28m23s (n=5) | 3m39s (n=3) | 1m20s | 10s |
| xiao_zero | 21m15s (n=9) | (in its suite) | 2m59s | 0s |
| c3_zero | 1h05m (n=4; last 1h33m) | (in its suite) | 38s | 0s |

Whole passes (`timings.csv`, lane `pass/pass`):

- **2026-11-25 12:00** (`9dc2b57f4`): six boards (the T-Deck, the three
  P4s and both Zeros), 48 min wall. The C3's suite took 47 min of it.
- **2026-11-26 01:44** (`656f37fd5`): every image built, the C3's suite
  alone, 96 min. The suite took 95 min.
- **2026-11-27 04:20** (`648ac49f8`): the C3 alone, 93 min.

### A2. Suite minutes by kind

From the junit files of the 2026-11-27 16:56 pass (`land`, `cb4fdba2f`),
`/tmp/board-pass/land-20261127-165630/`.

| kind | tdeck | guition_p4 |
|---|---|---|
| compiled tier (wasm, elf, wasi, fixtures, traps, front runs) | 8.3 | 10.1 |
| shell and UI flows | 2.0 | 1.8 |
| VM soft resets and stops | 2.0 | 1.5 |
| perf floors (Jet, hello, blit) | 1.6 | 1.8 |
| C-build conformance against the host | 1.3 | 1.8 |
| network (pkg, clock, Wi-Fi, BLE) | 1.1 | 0.8 |
| other | 0.6 | 1.1 |
| **total** | **16.9** | **18.9** |

### A3. The slowest tests (seconds)

**The consoles.** The 2026-11-27 16:56 pass. The CoreS3's whole suite
summed to 0.7 min (47 cases), its longest 8.8 s (the idle blank).

| tdeck | s | guition_p4 | s |
|---|---|---|---|
| twenty_soft_resets_leave_psram_flat | 98.9 | twenty_soft_resets_leave_psram_flat | 89.4 |
| the_scheduler_stops_a_runaway_service (failed) | 33.0 | elf_modules_run_isolated_in_u_mode | 60.2 |
| pkg_installs_a_cart_from_the_carts_repo | 32.8 | shift_last_and_copy_last_into_match_the_reference | 53.3 |
| custom_themes_derive_as_on_the_host | 29.4 | jet_showcase_…_half_width | 32.8 |
| jet_showcase_…_full_width | 29.3 | jet_showcase_…_full_width | 31.5 |
| jet_showcase_…_half_width | 29.2 | an_unsigned_cart_runs_natively_only_with_native_granted | 28.5 |
| the_picker_kernel_matches_sspr | 27.7 | a_drag_touches_no_storage_and_rebuilds_no_cache | 27.0 |
| a_doom_sized_file_is_skipped_when_current… | 24.3 | elf_commands_run_in_the_shell | 24.5 |
| an_unsigned_cart_runs_natively_only_with_native_granted | 23.4 | the_hello_wasm_cart_holds_its_floor | 24.4 |
| a_blit565_frame_goes_to_the_glass… | 22.6 | a_compiled_run_shows_its_frames_in_front | 24.1 |
| a_compiled_blit565_run_shows_its_frames_in_front | 21.9 | a_compiled_carts_written_files_outlive_its_session | 24.0 |
| the_pause_menu_dims_the_game_and_holds_the_heap | 21.5 | a_lua_cart_after_a_wasm_run_keeps_its_sram | 23.4 |
| the_hello_wasm_cart_holds_its_floor | 21.4 | the_picker_kernel_matches_sspr | 23.0 |
| a_compiled_cart_too_big_for_the_board_opens_the_notice | 19.3 | a_full_frame_blit_cart_holds_its_floor | 22.1 |
| a_compiled_app_reaches_its_roles_through_imports | 19.0 | the_showcases_frames_go_to_the_glass_from_the_cart | 21.7 |
| a_compiled_cart_for_a_newer_console_opens_the_notice | 18.2 | the_wm_meters_answer_for_the_frame_they_measured | 20.5 |
| vm_stops_leave_psram_flat_and_the_routes_read_back (failed) | 16.7 | a_frame_that_never_ends_is_ended[wasm] | 20.3 |
| a_full_frame_blit_cart_holds_its_floor | 16.7 | a_compiled_cart_too_big_for_the_board_opens_the_notice | 19.3 |
| a_frame_that_never_ends_is_ended[lua] | 15.5 | a_compiled_cart_out_of_native_stack_traps… | 18.8 |
| elf_commands_run_in_the_shell | 15.5 | a_compiled_cart_for_a_newer_console_opens_the_notice | 18.7 |

**The C3 Zero.** The 2026-11-27 02:46 pass (`land`, `648ac49f8`), 31
passed and 44 skipped in 93 min:

| test | s |
|---|---|
| zy_a_session_soak_keeps_the_board_s_ram | 891 |
| get_carts_installs_and_reinstalls_on_the_board | 520 |
| a_cart_uploaded_from_the_page_reads_back_byte_exact | 409 |
| the_fast_console_runs_through_the_secure_door | 330 |
| a_game_s_pmem_saves_are_back_after_a_reboot | 299 |
| a_second_browser_signing_in_displaces_the_first | 299 |
| the_page_reconnects_after_the_board_s_wifi_drops | 290 |
| the_page_reconnects_after_the_board_reboots | 288 |
| an_imported_cart_and_a_setting_survive_a_reset | 282 |
| the_page_manages_the_boards_wifi | 272 |
| chrome_boots_the_console | 252 |
| a_full_store_refuses_a_cart_says_so_and_corrupts_nothing | 189 |
| the_update_screen_shows_what_the_channel_offers… | 174 |
| a_closed_terminal_lets_ssh_in_while_the_page_stays | 156 |
| the_page_s_terminal_runs_the_board_s_shell | 152 |
| the_page_signs_in_and_asks_on_its_live_socket_alone | 151 |
| the_live_socket_answers_without_power_save | 149 |
| the_console_signs_in_and_syncs_a_cart | 138 |
| the_page_has_the_devices_its_board_relays | 127 |
| a_second_ssh_session_ends_the_first | 46 |

The XIAO's page scenarios cost the same order: `chrome_boots_the_console`
took 290 s and `the_page_has_the_devices_its_board_relays` 130 s
(2026-11-26 13:00, `livesvc`).

### A4. Noise, from the perf history

Read from `~/.cache/moybyte-perf/*.jsonl`, `after-suite` records,
2026-11-15..27, the last 15 a metric.

- **runMAD%** is the median absolute deviation between runs, relative to
  the median.
- **withinMAD%** is the median, over runs, of the same statistic across a
  run's own samples.

| board | metric | runs | runMAD% | withinMAD% |
|---|---|---|---|---|
| tdeck | Star Catcher fps | 15 | 0.2 | 0.0 |
| tdeck | Brick Siege fps | 15 | 0.7 | 0.7 |
| tdeck | Letter Blitz frame ms | 15 | 1.6 | 0.5 |
| tdeck | Jet Teapot uncapped fps | 15 | 0.3 | 0.9 |
| tdeck | Jet Teapot uncapped frame ms | 15 | 0.1 | 7.9 |
| tdeck | desk idle loop ms | 15 | 8.7 | 1.0 |
| tdeck | heap sram free | 15 | 0.0 | – |
| guition_s3 | Brick Siege fps | 15 | 0.7 | 0.5 |
| guition_s3 | Sky Run fps | 12 | 2.1 | 0.4 |
| guition_s3 | heap gc live | 15 | 11.5 | – |
| p4 | Star Catcher frame ms | 15 | 7.2 | 1.2 |
| p4 | Jet Teapot uncapped frame ms | 15 | 0.3 | 6.7 |
| p4 | window drag frame ms | 15 | 0.2 | 0.2 |
| guition_p4 | Brick Siege fps | 15 | 1.8 | 0.5 |
| guition_p4 | desk idle loop ms | 15 | 10.5 | 2.4 |
| elecrow_p4 | Jet Teapot uncapped fps | 5 | 0.3 | 7.7 |
| cores3 | heap sram largest | 8 | 37.0 | – |
| cores3 | Brick Siege fps | 8 | 0.2 | 0.1 |
| c3_zero | zero live rtt p90 | 7 | 34.1 | 26.0 |
| c3_zero | zero page root | 10 | 15.3 | 8.9 |
| xiao_zero | zero internal free idle | 5 | 0.4 | – |

More from the same history:

- **The desk idle.** Drawn fps, gc collections and longest pause read 0 in
  every record on every console.
- **The perf stage's phases** (the 2026-11-27 T-Deck record): about 18 s a
  roster cart, 36 s for Jet Teapot, 13 s for the desk idle, 142 s in all.

### A5. How often a band would have failed

Every `after-suite` metric reading from its sixth record on, against the
median of the ten before it, with the band of section 5 (unit floor, 4×
runMAD). This is the same history as A4.

| metrics | readings | past the band |
|---|---|---|
| fps and frame ms | 1,792 | 23 |
| heap | 641 | 39 |

Of the fps and frame-ms flags:

- Most are the 2026-11-22 steps that persisted. The Guition P4's window
  drag fps moved −37% and its frame ms +47%, and the Guition S3's PSRAM
  and gc-held moved in steps.
- The one-off readings just past the floor were Brick Siege fps −5.9% (the
  Guition P4), Letter Blitz fps −5.9% and Sky Run fps −6.3% (the Guition
  S3).

The heap flags are mostly gc live and gc held moving in whole-area steps.

### A6. Fresh against after-suite, same commit

`perf-baseline` records against the pass's records at the same image.
Relative change from fresh to after the suite:

| board, commit | sram free | sram largest | psram free | gc held | largest fps/ms change |
|---|---|---|---|---|---|
| tdeck `151c7c45` | −20.8% | −63.1% | −6.3% | 0.0% | +2.2% (Brick Siege frame) |
| tdeck `b909d0d9` | −20.3% | −63.1% | −14.4% | +50.0% | +6.2% (Letter Blitz frame) |
| tdeck `560f81f7` | −20.7% | −63.8% | −16.9% | +50.0% | −3.3% (Brick Siege fps) |
| tdeck `88eb2136` | −11.4% | −9.4% | −8.2% | 0.0% | +10.8% (Letter Blitz frame) |
| guition_s3 `667ef4d5` | −16.6% | −41.7% | −21.8% | +50.0% | +3.8% (Letter Blitz frame) |
| guition_s3 `b909d0d9` | −16.6% | −41.7% | −21.6% | +50.0% | +4.8% (Brick Siege fps) |
| p4 `667ef4d5` | −30.3% | −52.3% | −2.9% | 0.0% | +3.7% (Brick Siege frame) |
| p4 `b909d0d9` | −30.3% | −50.0% | −2.9% | 0.0% | −8.5% (window drag frame, better) |
| guition_p4 `667ef4d5` | −37.6% | −52.0% | −5.2% | 0.0% | −9.1% (window drag frame, better) |
| guition_p4 `b909d0d9` | −37.7% | −52.0% | −5.2% | 0.0% | +3.8% (Brick Siege Lua frame) |

### A7. The host suite

CI's run of dev on 2026-11-27 15:56 (`ci.yml`, run 46029259487):

- **Shards.** Four shards × Python 3.10 and 3.11. The 3.11 shards ran 694,
  638, 836 and 524 s serially, 14,421 tests passed between them, and each
  job took 11–19 min.
- **Preflight.** Its xdist lane, "suite (redraw excluded)", has a median of
  7m09s (`tools/timings.py --tool preflight`).

The slowest host tests in CI's 3.11 shards:

| test | s |
|---|---|
| test_frame_alloc.py::test_the_compiled_cart_is_the_run_being_measured (setup) | 160.9 |
| test_moy_ssh.py::test_a_large_exec_s_output_arrives_whole_to_a_fast_and_a_slow_reader | 66.6 |
| test_board_ports.py::test_a_rejected_chunk_names_the_chunk | 60.0 |
| test_moy_ssh.py::test_an_exec_that_leaves_its_stdin_unread_still_sends_its_output_whole | 51.7 |
| test_zero_heap.py::test_a_session_leaves_the_heap_as_the_start_left_it | 34.8 |
| test_uitree_aot.py::test_staging_compiles_the_staged_pages_and_names_a_stale_one | 26.7 |
| test_uitree_c_memory.py (setup) | 21.3 |
| test_uitree_c_micropython.py (setup) | 20.4 |

---

## Appendix B. The inventory (origin/dev `cb4fdba2f`, 2026-11-27)

**Boards.**

| letter | board | id |
|---|---|---|
| T | T-Deck | `tdeck` |
| S | Guition S3 | `guition_s3` |
| C | CoreS3 | `cores3` |
| W | Waveshare P4 | `p4` |
| G | Guition P4 | `guition_p4` |
| E | Elecrow P4 | `elecrow_p4` |

**Columns.**

- **s** is the T-Deck's time and then the Guition P4's, in seconds, from
  the 2026-11-27 16:56 pass (`-` where that board does not run it; a
  parametrised test is summed).
- **HW** says whether the check truly needs the board, by section 2's
  number.

A missing letter in "boards" is a hole the capability model closes unless
the board's toml declares the absence.

### B1. Boot, kernel, serial face

| test | boards | HW | host cover | s | verdict |
|---|---|---|---|---|---|
| the_kernel_lit_the_logo_before_any_vm | TSWGEC | 7 | – | 0/0 | KEEP |
| the_kernel_verifies_a_signed_manifest | TSWGEC | 1, 7 | `tests/test_moy_ota.py` (host build) | 0/0 | KEEP |
| the_frame_is_the_kernels | TSWGEC | 6 | – | 1/1 | KEEP |
| loop_is_the_kernels_line_with_every_stage | TSWGEC | 6 | – | 2/1 | FOLD → perf frame ms (reads the same LOOP line) |
| perf_line_is_the_one_format | TSGC | 6 | parse: `tests/test_moy_loop.py` | 5/5 | FOLD → perf (every PERF line the measurement reads is parsed) |
| perf_lines_flow | WE | 6 | – | -/- | DUP of the above |
| heapcaps_mem_and_hush_are_the_kernels_words | TSWGE | 5 | `tests/test_dev_channel.py` | 1/1 | KEEP |
| the_shell_answers_over_serial | TSWGEC | 1 | `tests/test_moy_sh.py` | 0/0 | KEEP, one check with the log word |
| the_log_word_reads_the_ring | TSWGEC | 1 | – | 0/0 | FOLD → the line above |
| the_shell_answers_with_the_vm_down | T | 1 | – | 8/- | KEEP, every board taking `moy_wasm` |
| py_probe_reaches_the_live_console | TSWGEC | – | – | 0/0 | DUP: the session fixture's own check |
| diag_toggle_roundtrips | TSWGEC | – | `tests/test_dev_channel.py` | 0/1 | HOST |
| state_snapshot_has_the_fullscreen_tier_shape | TSC | – | `tests/test_dev_channel.py` | 0/- | HOST |
| boots_to_the_desk | WGE | – | – | -/0 | DUP: the session's start |
| a_stale_handle_is_refused_loudly | TSWGE | 1 | spine twins | 0/0 | KEEP |

### B2. Panel, draw, flush

| test | boards | HW | host cover | s | verdict |
|---|---|---|---|---|---|
| draw_gates_are_installed | TSWGEC | 1 | – | 0/0 | KEEP |
| draw_gates_take_the_traffic | TSWGE | 1 | – | 2/2 | KEEP, add C |
| a_leaked_session_leaves_the_panel_flushing | TC | 2 | `tests/moy_flush_harness/` | 1/- | KEEP where the card shares the panel's bus |
| no_display_underruns | WGE | 2 | – | -/0 | KEEP, last in the session |
| the_ppa_composite_is_live | G | 1 | – | -/0 | KEEP for `esp32p4` |
| a_quiet_game_frame_rotates_one_rect | G | 1, 2 | – | -/11 | KEEP (rotated glass) |
| the_system_canvas_is_the_landscape_glass | S | 2 | – | -/- | DUP → one `the_panel_is_its_declared_glass` |
| the_system_canvas_is_landscape_on_portrait_glass | G | 2 | – | -/0 | DUP → the same |
| the_panel_is_the_landscape_glass | C | 2 | – | -/- | DUP → the same |
| a_failed_flush_is_recovered_from | S | 2 | – | -/- | KEEP, board-own |
| window_buffers_are_single_retained_surfaces | WGE | – | `tests/test_surface_model.py` | -/0 | HOST |
| window_chrome_freezes_during_a_content_scroll | WE | – | `tests/test_wm_content_freeze.py` | -/- | HOST |
| the_wm_meters_answer_for_the_frame_they_measured | WGE | 6 | – | -/21 | FOLD → the drag perf test |
| a_drag_touches_no_storage_and_rebuilds_no_cache | WGE | 4 | `tests/test_frame_alloc.py` | -/27 | FOLD → the drag perf test |
| idle_screen_blank_and_wake | TSWGEC | 2 | – | 9/10 | KEEP (the backlight) |
| the_saver_comes_and_its_wake_repaints | TSWGE | 2 | – | 5/6 | KEEP, add C |

### B3. Input

| test | boards | HW | host cover | s | verdict |
|---|---|---|---|---|---|
| swipe_rides_the_real_pointer_feed | TS | 2 | `tests/test_kinetic_scroll.py` | 3/- | KEEP as the one pointer-feed check, every touch board |
| a_long_press_opens_the_cards_verbs | TS | – | `tests/test_home_card_verbs.py` | 2/- | HOST |
| the_event_rings_keep_their_records | TSWGE | 1, 5 | – | 0/0 | KEEP, add C |
| a_gpio_lease_loses_no_tap | WGE | 2 | – | -/1 | KEEP on a `gpio` lease row |
| a_lease_runs_a_driver_and_a_crash_leaves_it_safe | WGE | 2 | – | -/2 | KEEP on the lease and `spi2` rows |
| the_homes_letter_keys_arrive_from_the_matrix | T | 2 | – | 5/- | KEEP, board-own |
| a_field_reads_the_matrix_and_mic_cancels_it | T | 2 | – | 6/- | KEEP, board-own |
| a_press_on_the_pad_reaches_the_console | C | 2 | – | -/- | KEEP → generic pad check |
| the_gamepad_answers_on_its_irq_line | C | 2 | – | -/- | KEEP → generic pad check |
| the_touch_controller_answers | C | 2 | – | -/- | KEEP → generic touch check |
| the_pointer_is_the_gsl3680 | G | 2 | – | -/0 | KEEP → generic touch check, board facts |
| the_hints_show_the_pads_keys | C | – | `tests/test_input_hint.py` | -/- | HOST+ (with the CoreS3's keys) |

### B4. Memory and the allocator

| test | boards | HW | host cover | s | verdict |
|---|---|---|---|---|---|
| twenty_soft_resets_leave_psram_flat | TSWGE | 5 | – | 99/89 | KEEP, n=6 (S1), add C |
| vm_stops_leave_psram_flat_and_the_routes_read_back | TS | 5 | – | 17/- | KEEP, every `moy_wasm` board |
| a_quiet_console_collects_its_garbage | TSWGE | 5 | – | 3/3 | KEEP, add C |
| a_quiet_console_leaves_a_live_heap_alone | TSWGE | 5 | – | 7/7 | KEEP, add C |
| mem_reports_the_heap | TSWGEC | 5 | – | 0/0 | FOLD → the perf start probe |
| the_pause_menu_dims_the_game_and_holds_the_heap | T | 5 | dim: `tests/test_modal_scrim.py` | 21/- | FOLD: the heap half stays, every board; the dim is HOST |
| a_card_transfer_takes_no_memory_of_its_own | TSWGEC | 4, 5 | – | 0/0 | KEEP |

### B5. Store, card, flash

| test | boards | HW | host cover | s | verdict |
|---|---|---|---|---|---|
| the_internal_volume_is_the_kernels | TSWGEC | 4 | `tests/test_moy_store.py` | 0/0 | KEEP |
| the_cart_store_is_the_card_when_one_mounted | SWGE | 4 | – | -/0 | KEEP on a card row (add C) |
| internal_flash_commits_under_a_running_cart | TSWGE | 4, 6 | – | 9/10 | KEEP, add C |
| leaving_paint_saves_a_stroke | TWGE | 4, 6 | `tests/test_paint_app.py` | 10/12 | KEEP (save time on real flash), add S, C |
| a_doom_sized_file_is_skipped_when_current_and_sent_when_not | TW | 4 | – | 24/- | KEEP every board (the push transport) |
| sync_push_writes_the_store_and_the_shelf_follows | S | 4 | – | -/- | KEEP, every board with a store |
| the_web_console_add_on_fits_this_image | TSWGEC | 4 | – | 0/0 | KEEP |
| every_system_app_claims_exactly_one_cart | TSWGEC | – | `tests/test_device_seed_parity.py`, `tests/test_app_registry.py` | 0/0 | HOST |
| appearance_cart_is_claimed | WGE | – | the same | -/0 | HOST |

### B6. Radio and network

| test | boards | HW | host cover | s | verdict |
|---|---|---|---|---|---|
| wifi_status_is_readable | TSWGEC | 3 | – | 0/0 | KEEP |
| wifi_is_off_at_rest | TSWGEC | 3 | – | 0/0 | KEEP |
| the_clock_syncs_when_the_network_comes_up | TSWGEC | 3 | – | 9/7 | KEEP |
| an_ntp_answer_reaches_the_clock_chip | C | 2, 3 | – | -/- | FOLD → generic RTC check |
| bluetooth_stops_and_starts_again | TSWGE | 3 | – | 9/12 | KEEP, add C |
| pkg_installs_a_cart_from_the_carts_repo | TSWGEC | 3, 4 | – | 33/16 | KEEP, the bench mirror (S7) |
| the_bar_wifi_widget_opens_the_wifi_panel | TWGE | – | `tests/test_top_bar.py`, `tests/test_wifi.py` | 8/8 | HOST+ |
| the_board_serves_its_web_console | C | 3 | – | -/- | KEEP, every board with `[web] console` |

### B7. OTA

| test | boards | HW | host cover | s | verdict |
|---|---|---|---|---|---|
| the_ota_updater_is_live_on_this_board | WGEC | 7 | – | -/0 | KEEP, add T, S |
| ota_verification_is_fast_enough | C | 6, 7 | – | -/- | KEEP |
| verification_is_fast_enough_to_not_think_about | WGE | 6, 7 | – | -/0 | DUP of the above |
| rollback_confirm_comes_from_the_frame_loop | C | 7 | – | -/- | KEEP |
| the_rollback_confirm_comes_from_the_frame_loop | WGE | 7 | – | -/0 | DUP of the above |
| a_pending_marker_becomes_a_verdict_on_this_board | WGE | 4, 7 | – | -/0 | KEEP, add T, S, C |

### B8. Services and the scheduler

| test | boards | HW | host cover | s | verdict |
|---|---|---|---|---|---|
| the_scheduler_stops_a_runaway_service | TSWGE | 1, 6 | `tests/test_restart_policy.py` | 33/3 | KEEP (the guard in C), add C |
| a_lua_service_runs_on_a_task_of_its_own | TSWGE | 1, 5 | – | 1/1 | KEEP, add C |
| a_lua_service_s_timers_run_through_a_vm_stop | S | 1 | – | -/- | KEEP, every `moy_wasm` board |
| a_lua_app_s_every_runs_beside_a_python_app_s | WE | 1, 6 | – | -/- | KEEP, every board |
| an_asyncio_service_runs_beside_the_desk | TSWGE | – | `tests/test_aio.py` | 3/3 | HOST+ (on the desktop MicroPython) |
| an_on_crash_service_restarts_after_a_forced_crash | TSWGE | – | `tests/test_restart_policy.py` | 2/3 | HOST+ (on the desktop MicroPython) |
| an_alarm_wakes_the_screen_and_at_logs | TSWGE | 2 | – | 9/10 | KEEP, add C |

### B9. Python and Lua cart runs

| test | boards | HW | host cover | s | verdict |
|---|---|---|---|---|---|
| a_cart_runs_and_exits | TSWGEC | 6 | – | 6/10 | KEEP + Star Catcher's perf |
| a_lua_cart_runs_and_exits | TSWGE | 6 | – | 6/9 | KEEP + Sakura Lua's perf, add C |
| a_front_run_makes_no_crossing | TSWGE | 1, 6 | – | 26/35 | KEEP + Brick Siege Lua's perf, add C |
| a_vm_free_frame_makes_no_crossing | TSWGE | 1, 6 | – | 26/35 | KEEP, add C |
| a_ctrl_c_ends_a_run_in_front_and_reaches_the_repl | TSWE | 1 | – | 13/- | KEEP |
| a_ctrl_c_ends_a_front_run_and_reaches_the_repl | G | 1 | – | -/17 | DUP of the above |
| a_lua_run_in_front_folds_to_the_glass | S | 2 | – | -/- | KEEP on banded glass |
| a_lua_tree_app_runs_on_the_engine | TSWGE | 1 | `tests/test_uitree_conformance.py` | 11/11 | KEEP, add C |
| a_run_off_the_shelf_keeps_the_vm_for_its_place | T | 5 | – | 5/- | KEEP, every `moy_wasm` board |
| open_settings_window, projects_opens, appearance_opens | WGE | – | `tests/test_desktop_shell.py`, `tests/test_projects_list.py` | -/7 | HOST |
| settings_rows_scroll_on_swipe, scroll_survives_release, settings_rows_fit_or_scroll | WEG | – | `tests/test_settings_scroll.py` | -/2 | HOST+ (release coast) |
| play_parks_the_windows_and_the_back_brings_them_back | WGE | – | `tests/test_wm_windowed.py` | -/4 | HOST |

### B10. The compiled tier (all need `moy_wasm` or `moy_elf`; "add C" on every row: the CoreS3 takes both)

| test | boards | HW | host cover | s | verdict |
|---|---|---|---|---|---|
| the_hello_module_runs_and_foreign_modules_are_refused | TSWGE | 1, 7 | – | 3/3 | KEEP |
| the_hello_wasm_cart_holds_its_floor | TSWGE | 6 | – | 21/24 | KEEP → history band |
| a_full_frame_blit_cart_holds_its_floor | TSWGE | 6 | – | 17/22 | KEEP → history band |
| the_jet_showcase_holds_its_floor_at_full_width | TSWGE | 6 | – | 29/32 | KEEP → the one Jet perf run |
| the_jet_showcase_holds_its_floor_at_half_width | TSWGE | 6 | – | 29/33 | KEEP, short window (S4) |
| doom_frames_match_the_host | SWGE | 1 | host CRCs | -/0 | KEEP where the fit allows |
| doom_runs_or_opens_the_notice | T | 5 | – | 0/- | KEEP |
| doom_runs_with_the_vm_down | TS | 5 | – | 15/- | KEEP |
| a_ctrl_c_during_a_stopped_run_reaches_a_vm | TS | 1 | – | 11/- | FOLD → doom_runs_with_the_vm_down (the same run) |
| a_compiled_frame_makes_no_crossing | TSWGE | 1 | – | 11/16 | KEEP |
| a_compiled_run_shows_its_frames_in_front | WGE | 2 | – | -/24 | KEEP |
| a_compiled_blit565_run_shows_its_frames_in_front | TS | 2 | – | 22/- | KEEP |
| a_compiled_palette_run_shows_its_frames_in_front | TS | 2 | – | 14/- | KEEP |
| a_blit565_frame_goes_to_the_glass_from_the_carts_memory | TS | 2 | – | 23/- | FOLD → the blit565 run above |
| a_palette_frame_goes_to_the_glass_from_the_carts_memory | TS | 2 | – | 14/- | FOLD → the palette run above |
| the_showcases_frames_go_to_the_glass_from_the_cart | WGE | 1, 2 | – | -/22 | FOLD → the Jet run |
| a_compiled_carts_palette_frames_are_written_into_the_canvas | WGE | 1, 2 | – | -/14 | KEEP for `esp32p4` |
| a_compiled_cart_too_big_for_the_board_opens_the_notice | TSWGE | 5 | – | 19/19 | KEEP (the real fit check) |
| a_compiled_cart_for_a_newer_console_opens_the_notice | TSWGE | – | `tests/test_api_level.py`, `tests/test_wasm_cart.py` | 18/19 | HOST |
| a_compiled_cart_with_no_module_runs_on_the_interpreter | TSWGE | 1 | – | 8/13 | KEEP (the interpreter tier really running) |
| a_module_for_another_chip_runs_on_the_interpreter | TSWGE | – | `tests/test_cart_store.py` | 9/14 | HOST+ (the file choice) |
| a_stale_format_module_runs_on_the_interpreter | TSWGE | – | `tests/test_cart_store.py` | 9/14 | HOST+ (the file choice) |
| a_compiled_cart_whose_module_was_tampered_with_is_refused | TSWGE | 7 | – | 8/8 | KEEP (the image's key) |
| an_unsigned_cart_runs_natively_only_with_native_granted | TSWGE | 7 | `tests/test_app_perms.py` | 23/28 | KEEP |
| consent_lets_only_a_missing_signature_through | TSWGE | 7 | `tests/test_app_perms.py` | 0/0 | KEEP |
| a_misaligned_load_or_store_of_any_width_is_exact | TSWGE | 1 | – | 0/0 | KEEP |
| a_saturating_float_to_int_conversion_is_exact | TSWGE | 1 | – | 0/0 | KEEP |
| the_run_stack_works_in_psram_and_internal_sram | TSWGE | 5 | – | 1/1 | KEEP |
| terminate_reaches_a_runaway_only_at_its_end | TSWGE | 1, 6 | – | 4/2 | KEEP |
| a_frame_that_never_ends_is_ended | TSWGE | 6 | – | 29/38 | KEEP |
| a_stuck_run_with_the_vm_down_is_ended | TS | 6 | – | 7/- | KEEP |
| a_trap_in_init_is_the_carts_own_error | TSWGE | 1 | – | 12/18 | KEEP |
| a_trap_in_init_with_the_vm_down_is_the_carts_own_error | TS | 1 | – | 12/- | KEEP |
| a_compiled_cart_out_of_native_stack_traps_with_its_numbers | WGE | 1 | – | -/19 | KEEP, add T, S |
| a_cart_s_timed_lanes_run_and_a_runaway_is_struck | WGE | 1, 6 | – | -/50 | KEEP, add T, S |
| par_items_across_the_cores_match_them_in_order | TSWGE | 1 | – | 11/17 | KEEP |
| a_folder_in_the_cart_reads_as_a_missing_file | TSWGE | 4 | – | 8/13 | KEEP |
| a_compiled_carts_written_files_outlive_its_session | TSWGE | 4 | – | 13/24 | KEEP |
| a_lua_cart_after_a_wasm_run_keeps_its_sram | TSWGE | 5 | – | 11/23 | KEEP |
| the_wasm_engine_costs_the_idle_desk_at_most_a_constant | TSWGE | 5 | – | 1/2 | KEEP |
| a_run_with_wifi_and_ble_up_costs_at_most_a_constant | TSWGE | 3, 5 | – | 4/4 | KEEP |
| load_unload_loop_under_a_live_cart_and_wifi | TSWGE | 3, 5 | – | 10/9 | KEEP |
| a_compiled_app_reaches_its_roles_through_imports | TWE | 1 | – | 19/- | KEEP, add S, G |
| a_compiled_app_draws_the_toolkits_widgets | TWE | 1 | – | 15/- | KEEP, add S, G |
| wasi_commands_run_in_the_shell | TSWGE | 1 | – | 15/12 | KEEP |
| elf_commands_run_in_the_shell | TSWGE | 1 | – | 15/25 | KEEP |
| elf_modules_run_isolated_in_u_mode | WGE | 1 | – | -/60 | KEEP for `esp32p4` |

### B11. C-build conformance against the host (each batched on the board, S5)

| test | boards | HW | host cover | s | verdict |
|---|---|---|---|---|---|
| the_painter_matches_the_host | TSWGE | 1 | the host frame is the reference | 1/2 | KEEP, add C |
| the_sprites_match_the_host | TSWGE | 1 | the same | 3/5 | KEEP, add C |
| the_picker_kernel_matches_sspr | TSWGE | 1 | the same | 28/23 | KEEP, batched |
| shift_last_and_copy_last_into_match_the_reference | TSWGE | 1 | the same | 8/53 | KEEP, batched (the 2D-DMA on a P4) |
| a_fuzzed_font_corpus_loads_as_on_the_host | TSWGE | 1 | the same | 9/6 | KEEP, batched |
| a_fuzzed_layout_corpus_reads_as_on_the_host | TSWGE | 1 | the same | 1/1 | KEEP |
| the_glyph_lane_draws_the_hosts_bytes | TSWGE | 1 | the same | 1/0 | KEEP |
| custom_themes_derive_as_on_the_host | TSWGE | 1 | `tests/test_theme_derive.py` | 29/18 | KEEP, batched |
| the_theme_font_is_installed | TSWGE | 4 | – | 0/0 | KEEP, add C |
| the_font_set_is_the_tiers | TSWGE | – | `tests/test_make_font.py` | 1/1 | HOST+ (the staged set) |

### B12. Board-own hardware (the CoreS3's file; generic checks after P2)

| test | HW | s | verdict |
|---|---|---|---|
| brightness_steps_the_axp2101s_light | 2 | 0.2 | KEEP → generic backlight check |
| the_battery_reads_the_axp2101 | 2 | 0.0 | KEEP → generic battery check |
| the_amplifier_is_up_and_named | 2 | 0.0 | KEEP → generic speaker check |
| the_microphone_reads_samples | 2 | 0.3 | KEEP → generic mic check |
| the_clock_chip_keeps_the_time | 2 | 0.0 | KEEP → generic RTC check |
| the_led_bar_takes_a_frame_and_goes_dark | 2 | 0.0 | KEEP → generic LED-bar check |
| the_led_bar_is_a_processs_and_dark_when_it_ends | 2 | 0.0 | FOLD → the line above |

(Times here are the CoreS3's, from the same pass.)

### B13. The Zero suite (`tests/test_zero_on_glass.py`; times are the C3's, 2026-11-27 02:46, in seconds)

| test | HW | host cover | s | verdict |
|---|---|---|---|---|
| improv_over_the_cable_joins_a_board_with_no_network | 3 | `tests/test_zero_glass.py` | 17 | KEEP |
| sync_names_the_pack_the_image_names | 4 | – | 0 | KEEP |
| the_root_and_what_a_page_load_costs_the_board | 3, 5, 6 | – | 2 | KEEP (perf) |
| chrome_boots_the_console | 3, 6 | – | 252 | KEEP, the module's one page boot (Z3) |
| the_console_signs_in_and_syncs_a_cart | 3, 4 | – | 138 | KEEP, on the shared page |
| a_claim_sets_the_password_and_ssh_answers_at_once | 3 | – | 38 | KEEP |
| the_live_socket_answers_without_power_save | 3, 5, 6 | – | 149 | KEEP (perf: rtt, internal RAM) |
| the_page_signs_in_and_asks_on_its_live_socket_alone | 3 | the route table: `tests/test_live_requests.py` | 151 | KEEP the socket; the route-by-route refusal is HOST+ |
| the_page_s_requests_ride_its_live_socket | 3 | – | 316 (XIAO) | KEEP, on the shared page |
| a_pin_write_reaches_the_pin_and_comes_back | 2, 3 | – | 289 (XIAO) | KEEP where the roster has Pin Light |
| moy_mesh_s_window_on_the_page_reaches_its_service_on_the_board | 2, 3 | – | (skipped) | KEEP on a `lora` row |
| moy_mesh_on_the_page_and_on_a_tdeck_talk_over_lora | 3, 8 | – | (skipped) | KEEP → pair stage |
| moy_mesh_holds_the_board_s_radio_from_the_page | 3 | – | (skipped) | KEEP on a `lora` row |
| the_page_s_terminal_runs_the_board_s_shell | 3 | `tests/test_moy_sh.py` | 152 | KEEP, on the shared page |
| a_closed_terminal_lets_ssh_in_while_the_page_stays | 3 | – | 156 | KEEP |
| the_fast_console_runs_through_the_secure_door | 3 | – | 330 | KEEP |
| the_page_manages_the_boards_wifi | 3 | – | 272 | KEEP |
| edit_and_vi_save_what_was_typed_over_ssh | 5 | `tests/test_moy_ssh.py` | 26 | FOLD → one SSH session test, heap per step |
| a_pipe_carries_a_stream_past_its_memory_whole | 5 | `tests/test_moy_ssh.py` | 28 | FOLD → the same |
| find_du_and_rm_walk_a_deep_folder | 4 | `tests/test_moy_sh.py` | 19 | FOLD → the same |
| cat_of_a_64_kb_file_arrives_whole | 3, 5 | `tests/test_moy_ssh.py` | 37 | FOLD → the same |
| a_second_ssh_session_ends_the_first | 3 | `tests/test_moy_ssh.py` | 46 | FOLD → the same |
| a_cart_uploaded_from_the_page_reads_back_byte_exact | 3, 4 | – | 409 | KEEP, on the shared page |
| a_game_s_pmem_saves_are_back_after_a_reboot | 4 | – | 299 | FOLD → one reboot test (Z4) |
| an_imported_cart_and_a_setting_survive_a_reset | 4 | – | 282 | FOLD → the same |
| the_page_reconnects_after_the_board_reboots | 3 | – | 288 | FOLD → the same |
| the_page_reconnects_after_the_board_s_wifi_drops | 3 | – | 290 | KEEP |
| a_full_store_refuses_a_cart_says_so_and_corrupts_nothing | 4 | `tests/test_cart_store.py` | 189 | KEEP (the real filesystem full) |
| the_update_screen_shows_what_the_channel_offers_without_installing | 3, 7 | – | 174 | KEEP, on the shared page |
| a_second_browser_signing_in_displaces_the_first | 3 | – | 299 | KEEP (a second browser on purpose) |
| the_board_answers_at_its_mdns_name | 3 | – | 0 | KEEP |
| the_board_s_clock_is_set_from_the_network | 3 | – | 3 | KEEP |
| get_carts_installs_and_reinstalls_on_the_board | 3, 4, 5 | – | 520 | KEEP, heap through `look()` (Z2) |
| the_page_has_the_devices_its_board_relays | 3 | – | 127 | KEEP, on the shared page |
| the_page_plays_a_match_against_a_console | 8 | – | (skipped) | KEEP → pair stage |
| the_console_s_atan2_is_the_wasm_s | 1 | – | (skipped) | KEEP → pair stage |
| works_offline_installs_the_console_and_remove_takes_it_back | 3, 4 | – | (XIAO) | KEEP on an online console with an updater |
| zy_a_session_soak_keeps_the_board_s_ram | 5 | – | 891 | FOLD → the suite-wide drift trace (Z1; owner decision 3) |
| zz_the_board_is_given_back | – | – | 12 | FOLD → the session's teardown |
