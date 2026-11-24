# Contributing to Moybyte

Thanks for your interest! First, the promise that governs everything here:

> **Everything you'd do as a person is free, forever.** Run the simulator,
> flash the firmware on your own board, modify it, teach with it, make and
> sell your own carts. The only thing that needs a commercial license is
> selling hardware or a competing commercial product built on the console —
> and even that restriction expires per release after two years. See
> [`LICENSE.md`](LICENSE.md).

## Which branch

**Branch off `dev`, and target `dev` with your PR.** `dev` is where work lands;
`master` is the tested tree that people's boards actually run — the project
site flashes it and the stable over-the-air channel offers it, so a change gets
there only after a maintainer has tested it on the hardware it touches (the
merge into `master` is the release, and it bumps the firmware version).

Builds off `dev` are published as **beta** firmware, which is how a change can
be tried on a real board before it is anyone's default. GitHub still shows
`master` by default, so a PR opened from a fork may need its base switched.

## Before you start

- **Bugs / small fixes:** open an issue or a PR directly.
- **Features:** open an issue first. The console is deliberately small and
  opinionated ("learn to make", not "learn to use": `docs/os_2026-11.md` §2);
  a quick design conversation saves you from building something we can't
  merge.
- **Carts:** carts you author are **yours** — license them however you like.
  To offer one for the console, see
  [moybyte-org/carts](https://github.com/moybyte-org/carts); a store for
  user carts is #122. A game needs only the cart API (moy-spec's SPEC.md,
  Moybyte's page of it `docs/moy_cart_api.md`); an app for the console is
  written against `docs/app_api_v1.md`, whose UI tree is the one way an app
  draws its interface.

## Developer Certificate of Origin (DCO)

Because the console is under a source-available license (FSL) that the project
also licenses commercially, we need to know every contribution is yours to
give. We use the [Developer Certificate of Origin](https://developercertificate.org/)
— no CLA paperwork, just sign off each commit:

```bash
git commit -s
```

This appends `Signed-off-by: Your Name <you@example.com>`, certifying you
wrote the change (or have the right to submit it) and that the project may
distribute it under its licenses, including the FSL's future-MIT grant and
commercial licensing. PRs without sign-off can't be merged.

## Development

```bash
make setup          # .venv + editable install (the dev + sim extras)
make test           # pytest, the fast loop
make preflight      # what CI runs, in CI's order: the gate before you push
.venv/bin/python tools/simulate_desktop.py   # the console itself, on your PC
```

The host side needs Python 3.10 or 3.11 (CI tests both), a C compiler and git:
the simulator runs the boards' C library, and `make test` builds a desktop
MicroPython. `make preflight` runs `tools/preflight.sh`, which needs Docker: it
runs the host suite in CI's own image (ubuntu 26.04, Python 3.11,
`tools/ci_image/`), and `--native` runs it on your OS instead. It adds the
browser lane when your change reaches the web console and every board's image
when it reaches firmware; its header lists the lanes and why their order
matters. `make test` alone is not the CI job.

`CLAUDE.md` is the map of the repository (for people as much as for AI tools):
which doc is the authority for what you are about to touch, and the rules that
bite there. Three of them catch newcomers:

- **Host and device are one codebase.** Every tier draws through one canvas
  class, `device_canvas.DeviceCanvas` (`device/device_canvas.py`), which the
  host runs through `runtime/host/host_canvas.py`. A drawing change lands
  there, or one cart stops looking the same everywhere.
- **Docs say what IS**, in the present tense, and change with the behaviour
  they describe. A measured number lives in an issue or a generated ledger
  under `docs/perf/`, never in prose. `make test` runs `tools/check_docs.py`.
- **Boards:** each lives in its own directory under `firmware/`, whose README
  is the authority on its hardware, build and flashing. Flashing needs
  `.venv/bin/python -m pip install -e '.[device]'` (esptool, pyserial); a
  board image needs ESP-IDF, which each board's build fetches at its pinned
  version. Untested on a board is fine for a change that reaches firmware;
  say so in the PR and the maintainers flash and verify.

Match the surrounding code's style; tests go in `tests/`.

## Opening the PR

Branch off `dev`, merge the current `dev` in before you open the PR
(`git fetch origin && git merge origin/dev`; in a fork, the remote that points
here), and fill in the checklist of the
[pull request template](.github/pull_request_template.md). CI's "PR base" check
fails a branch that does not contain `dev`'s tip, because everything else in CI
then tests a tree that is not the one being merged.

## What we're unlikely to merge

Features that fight the positioning (`docs/os_2026-11.md` §2): an account
for local use, a console whose point is consuming rather than making, or
anything that breaks the fixed 320×240 indexed game canvas that lets one cart
run on every tier.
