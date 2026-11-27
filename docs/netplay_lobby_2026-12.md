# Netplay lobby (2026-12): a match forms from a choice

**The PLAN for how two players choose to play together** (owner's direction,
2026-11-27). `docs/netplay_v1.md` is the contract for what is built; this
doc is the design that replaces its same-cart pairing, and a phase that
lands moves its rules into netplay_v1.md and cuts them from here. The order
of work and its state are **#350** ("Multiplayer lobby"). The radio service
it runs on, its two lanes and the rules for asking a person are
`docs/os_2026-11/between_apps.md` §6.

## 0. The owner's direction (2026-11-27)

- A two-player game opens on a menu: **1 Player**, **2 Players – nearby
  console**, **2 Players – same screen**; the last is greyed out when no
  second input (a Bluetooth keyboard or gamepad) is connected.
- A match forms from that choice, never by itself. Forming by itself is why
  a match "never ended" and re-paired after a restart: a console that came
  back on the same cart met its old peer and formed again.
- Nearby play is Nintendo DS local wireless: a host offers a session, or
  invites someone; nearby consoles see the session in a list and join; the
  host starts when everyone is in. Download Play: a console without the game
  joins by receiving it, which is beaming (`docs/netplay_v1.md` §7).

## 1. The player's flow, screen by screen

Every screen below is an OS page drawn through the toolkit (the
`confirm_ui` dialog's way: `uitree_app.hosted_page`), so one layout serves
the T-Deck's 320×240 and the keys, and the touch desks. On keys: up/down
move the focus, Enter or A takes the row, Esc or B goes back one screen. On
touch: a row is a full-width tap target and back is the bar's back.

### 1.1 The Players sheet

A cart that plays two (§2) opens on this sheet instead of its first frame,
from the shelf, a card's PLAY and Editor PLAY alike. The cart has not
started: backing out returns to where it was launched, and nothing ran.

```
 BRICK SIEGE
 > 1 PLAYER
   2 PLAYERS · NEARBY CONSOLE
   2 PLAYERS · SAME SCREEN          (grey)
     Connect a second keyboard or gamepad
```

- The focus opens on the row chosen last time for this cart while that row
  is live, else on 1 PLAYER. One press on a live row goes on; nothing else
  asks.
- A grey row keeps its focus and shows why under it, and takes no press:
  SAME SCREEN when no second input is connected (§5 says what counts per
  board); NEARBY CONSOLE when this console's link cannot come up (the
  Guition P4's C6 without its shim, a failed bring-up: the rule §7's SEND
  follows) or a beam is under way.
- NEARBY CONSOLE is absent, not grey, for a cart that does not ask for
  `multiplayer`: that is the cart's property, not the board's.
- 1 PLAYER runs the cart with `players()` 1 and arms no radio.

### 1.2 Nearby: host, or join a game nearby

NEARBY CONSOLE opens one screen that is both choices, so a session already
on offer is one press away:

```
 BRICK SIEGE · NEARBY
 > HOST A GAME
   Games nearby
   Ana's T-Deck              ▂▄▆
   Ben's CoreS3   2/2 full   ▂▄     (grey)
   Cy's Waveshare  version 21 · get it   ▂
   Dee's Guition  needs an update     (grey)
```

- A row is a session of THIS cart offered nearby: the host console's name
  (the name set in Settings) and its signal, strongest first, re-sorted as
  signals move without moving the focused row. A board whose radio gives no
  signal reading draws no bars: absence, never an empty meter.
- A full session is grey. A session of another version of the cart reads
  "version N · get it", and joining it takes the host's copy first (§1.6). A
  console on the older protocol reads "needs an update" and cannot be
  joined (§3.6).
- With nothing heard the list says "Looking for games nearby…". While this
  screen is open a person is watching it, so the console walks the probe
  channels as a beam's receive state does (`docs/netplay_v1.md` §2, the
  probes), and a session pinned to an AP's channel is found.
- Choosing a session sends a JOIN and opens the guest's lobby (§1.4).
  HOST A GAME opens the host's lobby (§1.3).

### 1.3 The host's lobby

```
 HOSTING BRICK SIEGE
 as Nikola's T-Deck
  1  Nikola's T-Deck  (you)
  2  waiting…
 Invite
 > Ben's CoreS3      ▂▄▆   INVITE
   Dee's Guition     ▂▄    declined
 [ START ]  (grey until 2/2)   [ CANCEL ]
```

- The lobby is named by the host's console and the cart. Its slots are the
  cart's players capped at the lockstep's two.
- A guest's JOIN fills a slot as it lands; the slot reads its console's name,
  and "getting the game 40%" while a guest without the cart receives it
  (§1.6). A guest counts as in once its slot says ready.
- Invite lists the consoles heard nearby that are not in this lobby (§3.2,
  presence). Enter or a tap on one sends it an invitation; its row then reads
  "invited…", then "declined", "busy" (it is in a match) or nothing more
  once it joins. An invitation the other side never answers reads
  "declined" after the invitation's wait (§1.5).
- START is live when every slot is filled and ready. It sends START (§3.4)
  and both consoles run the cart from frame zero.
- CANCEL closes the session: the guests hear CLOSE (§3.3) and the host is
  back on the Players sheet.

### 1.4 The guest's lobby

```
 BRICK SIEGE
 Joined Ana's T-Deck
  1  Ana's T-Deck
  2  Nikola's T-Deck  (you)
 Waiting for Ana to start…
 [ LEAVE ]
```

The guest's console holds no game state and runs no cart until START. LEAVE
says so to the host and returns to Nearby.

### 1.5 An invitation arriving

An invitation is a question the OS asks over whatever is in front, as a
beam's offer is (`docs/os_2026-11/between_apps.md` §6):

```
 Ana's T-Deck invites you to play Brick Siege
 (not on this console: 1.2 MB from Ana)
 [ ACCEPT ]  [ DECLINE ]  [ BLOCK THIS CONSOLE ]
```

- ACCEPT leaves what is in front as launching a cart from the shelf would
  (a running cart closes by its own rules, an unsaved Editor asks first) and
  opens the guest's lobby joined to the host. A missing or other-version cart
  is fetched first (§1.6); the question already said its size, so nothing
  asks again.
- DECLINE answers NO. BLOCK mutes that console for good, kept in
  `system/settings` beside beaming's blocks, and answers nothing.
- The question withdraws after the invitation's wait (`MOY_MATCH_INVITE_WAIT_MS`,
  configuration), which counts as a decline.
- The flood rules are beaming's, one count per sender for both kinds of
  question: three declines or time-outs in a row mute that sender for a
  doubling window up to a day, an accept resets it, and the console caps
  the questions it asks a minute whoever sends.
- A console in a live match is not asked: its radio service answers BUSY and
  the host's row says so. A console whose Nearby screen or lobby is open
  hears the invitation inside that screen as a row at the top of its list,
  not as a dialog over it.

### 1.6 A guest without the cart: Download Play

A console reaches a session for a cart it lacks two ways: by accepting an
invitation, or through the system menu's **PLAY NEARBY** row (beside RECEIVE
NEARBY), which lists every session nearby of any cart. There a missing cart's
row reads "Brick Siege · get 1.2 MB", and taking it asks once: "Get Brick
Siege from Ana's T-Deck? 1.2 MB" — GET / NO.

Then:

1. The guest JOINs saying it needs the cart; the host fills the slot as
   "getting the game" and beams the cart to it (`docs/netplay_v1.md` §7's
   stream, on the reliable lane once #350 phase 2 lands). The JOIN is the
   guest's consent, so the beam binds to the host without a receive state.
2. Both consoles show the beam's progress and time left (§7's terms): the
   guest in its lobby, the host in the guest's slot. Either side can stop
   it; a stop leaves the lobby.
3. The cart lands as a cart that arrived as files, and its first-run ask
   (`docs/os_2026-11/processes.md` §2) comes up on the guest before it says
   ready. NO there is a LEAVE.
4. The slot says ready and the host's START is live.

A session of another version is joined the same way: the host's copy lands
over the guest's as an update of that cart, because two versions cannot run
one lockstep world.

### 1.7 Leave, disconnect, restart and pause

| what happens | the console it happens on | the other console |
|---|---|---|
| a guest LEAVEs a lobby | back to Nearby | the slot reads "Ben left", then "waiting…" |
| the host CANCELs | back to the Players sheet | "Ana closed the game", back to Nearby |
| a lobby member goes silent (`MOY_MATCH_PEER_TTL_MS`) | — | guest: "Lost Ana's T-Deck", back to Nearby; host: the slot frees |
| Quit in a match (pause menu) | home | the end card: "Ana left the game" |
| a console vanishes in a match (reboot, power, range) | it boots to its desk; nothing forms again, because nothing forms by itself | the give-up (`docs/netplay_v1.md` §3), then the end card: "Lost Ana's T-Deck" |
| BACK TO LOBBY in a match (pause menu, either side) | both consoles return to the lobby with the same slots | the host can START again (a rematch), a guest can LEAVE |
| RESTART MATCH (pause menu, host only) | a new START in the same lobby: both run from frame zero | a notice: "Ana restarted the match" |
| Restart from the dev channel or Editor PLAY | the match ends (BYE), as today | the end card |
| a console pauses | its ticks stop; its input packets say paused | its ticks stall where lockstep stalls them, at most the delay later, under "Ana paused" instead of "waiting"; the give-up does not count while the paused flag is heard, and its own pause menu still offers QUIT and BACK TO LOBBY |

**The end card** replaces the automatic solo re-run: "Ana left the game" or
"Lost Ana's T-Deck", with PLAY SOLO (the cart from frame zero, 1 Player),
BACK TO LOBBY (the host's lobby with the slot free; a guest's Nearby) and
QUIT. It is a screen that says why and waits for its person, which
`docs/netplay_v1.md` §3's rule allows; the frozen screen with no
explanation stays designed out. A guest's pause menu has no RESTART: a
lockstep world restarts on both consoles or on neither.

## 2. Who owns what: the sheet is the OS's

**The menu is an OS sheet the console shows before the cart starts. A cart
asks for it with a Moybyte-side manifest field, not a verb.**

- **One cart API.** A cart sees `players()` and `btn(name, i)` and never
  learns where pad two came from (`docs/netplay_v1.md` §6). Hosting,
  joining, invitations, signal and Download Play are where pad two comes
  from. A cart-drawn menu would make every one of them a cart verb, in the
  public table Python and Lua must agree on verbatim (`docs/moy_cart_api.md`,
  SPEC.md in moy-spec), for every moy host to implement or stub, and every
  two-player cart would draw its own lobby.
- **Frame zero.** Lockstep needs both worlds to start from the same first
  frame. A sheet before the cart starts gives that for free: no world exists
  until START. A menu inside the cart means the world is already running
  when the match forms, which is the re-run-in-place `docs/netplay_v1.md`
  §3 and §4 spend paragraphs guarding.
- **Every tier at once.** Python, Lua and compiled carts get the same sheet,
  and so does the page a Zero serves; a cart-drawn menu is written per cart.

**The field: `moybyte.players`**, the most players the cart plays. It is
read by the console only, so it needs no moy-spec change: SPEC.md §3.1 has
every host ignore a manifest field it does not know, and a Moybyte feature
goes in a Moybyte-side field (CLAUDE.md, where a piece belongs). SPEC.md's
input section asks that local multiplayer degrade cleanly and never be a
thing a cart must declare; the field keeps that, because it refuses no
console and the cart still asks `players()` at run time.

- Absent, it is 2 for a cart that asks for `multiplayer` and 1 otherwise, so
  every two-player cart today gets the sheet with no edit.
- 1: no sheet. 2 or more: the sheet, with NEARBY CONSOLE only where the cart
  asks for `multiplayer`, which stays the gate on the radio and on `net`.
- Brick Siege and Harpoon Pop keep their one-tank-per-player code: the sheet
  decides what `players()` answers before `_init` runs.

A cart-drawn menu, or a verb to ask for a match from inside a running cart,
would be a moy-spec change (a new verb in SPEC.md, `moy-api.lua` and the
conformance suite); this design needs neither.

## 3. The wire

### 3.1 The protocol goes to 4

`MOY_MATCH_PROTO` becomes 4 with the lobby, because the beacon's meaning,
JOIN, START and the input packet all change. The standing rule holds:
consoles on different protocols do not hear each other's frames
(`moy_match_dispatch` drops another version), so an old console can neither
auto-form with a new one nor take its START. One exception, for the person:
a new console parses a protocol-3 beacon far enough to list its sender as
"needs an update" (§1.2) and never answers it. Beaming and ports go with the
bump, so consoles on the two sides of it neither match nor beam until both
take the release that carries it.

**The payload rule stands: inputs, never state.** Lobby frames carry names,
ids, slots and readiness; the seed and the host's tuning ride START as they
do today, and nothing of the cart's world crosses.

### 3.2 Beacons: presence and sessions

Today's beacon (`name|board|cart|hz|ch`, sent while the link is up) says
which cart a console sits on, and two beacons on one cart form a match. In
protocol 4 the beacon says what the console is doing, and forms nothing:

| state byte | sent while | cadence | fields after `name\|board` |
|---|---|---|---|
| 0 idle | the radio service runs and the console is visible (§7, decision 2) | `MOY_MATCH_PRESENCE_MS` | none |
| 1 looking | Nearby, PLAY NEARBY or a lobby is open | `MOY_MATCH_BEACON_MS` | `hz\|ch` |
| 2 playing | a match is live | `MOY_MATCH_BEACON_MS` | `hz\|ch` |
| 3 hosting | the host's lobby is open | `MOY_MATCH_BEACON_MS` | `title\|hz\|ch\|id\|version\|lobby\|have/want\|size` |

- `lobby` is a 32-bit id the host draws when it opens the lobby; `id` and
  `version` are the cart's manifest `id` and `version`, so a session is one
  build of one cart, never a title (two carts sharing a title cannot meet);
  `size` is the cart's byte size for Download Play, 0 where it cannot be sent.
- **Signal.** The link records each frame's RSSI (`moy_link.c`'s record
  gains it; the C6 shim's receive passes it from the shim version that
  carries it; the page gets it from its board, §4), and a peer row keeps a
  smoothed reading the screens draw as bars. A link that gives none leaves
  the reading None.
- **Channels** follow `docs/netplay_v1.md` §2 unchanged: a host's lobby
  rests on its channel (home, or its AP's when pinned), a looking console
  walks the probe list, and a joined guest rests where its host is heard, as
  a bound beam does.

### 3.3 The lobby's frames

| frame | from → to | carries | said |
|---|---|---|---|
| JOIN (2) | guest → host | host MAC, lobby id, hz, needs-cart flag | until the host's ROSTER names the guest |
| LOBBY (9) ROSTER | host → its guests | lobby id, each slot's MAC, name and ready flag | on every change and every beacon tick |
| LOBBY FULL | host → a joiner | lobby id | once per JOIN |
| LOBBY READY | guest → host | lobby id | until the ROSTER shows the slot ready |
| LOBBY LEAVE | guest → host | lobby id | `MOY_MATCH_BYE_SENDS` times |
| LOBBY CLOSE | host → its guests | lobby id | `MOY_MATCH_BYE_SENDS` times |
| LOBBY BACK | either → the other, in a match | lobby id, session | `MOY_MATCH_BYE_SENDS` times: the session ends, the lobby stays |
| INVITE (10) ASK | host → one console | lobby id, host name, title, id, version, size, channel | until answered or `MOY_MATCH_INVITE_WAIT_MS` |
| INVITE YES / NO / BUSY | invited → host | lobby id | once per ASK heard (a YES is followed by a JOIN) |

Every frame is broadcast with its destination in the payload, as the
handshake is today (`docs/netplay_v1.md` §2: unicast from an unregistered
peer vanishes). Lobby state is re-said by its owner until the other side's
own frame shows it taken (the ROSTER is the host's answer to JOIN, READY and
LEAVE), the receiver-driven shape the ack's lies forced on beaming. On the
reliable lane (#350 phase 2) INVITE and the LOBBY kinds move onto it and
their re-saying becomes the lane's; until then they work as above, so the
lobby does not wait for the lane.

**Who is heard** (`moy_match.h`, WHO IS HEARD) narrows: a JOIN is taken only
for the lobby this console hosts, a ROSTER, CLOSE or START only from the host
of the lobby this console joined, by MAC and lobby id, and port 0's `net`
messages outside a match only from a member of that lobby. An INVITE ASK is
taken by the radio service whatever runs, under the flood rules (§1.5).

### 3.4 The handshake into lockstep

START keeps its layout (session, index, seed, the destination MAC, the
match's tick, the title and the host's tuning) and gains the lobby id. The
host sends it when its person presses START; the guest, whose console
already sits in that lobby with no cart running, builds the session and
opens the cart, so neither side re-runs anything. The host chases START
until the guest's first input lands (`MOY_MATCH_START_TRIES`), and an
unanswered START returns both to the lobby with "Ben didn't start" rather
than running solo. The tick (the lower of the two consoles' word, carried
in the beacon and the JOIN), the opening delay (a page's
`MOY_MATCH_PAGE_DELAY_MS`), the world check and the step down are the
session's and do not change. RESTART MATCH is a new START with the next
session id; BACK TO LOBBY ends the session and keeps the lobby.

### 3.5 The input packet's paused flag

The input packet's header gains a paused bit. A paused console stops
sampling and ticking, and its between-ticks resend (`docs/netplay_v1.md` §2)
keeps saying its newest frame with the bit set. The peer simulates the
frames it holds inputs for and stalls on the next, which is lockstep's own
stop, so both worlds stop on frames each one has inputs for, without a frame
agreed in advance. While the bit is heard the peer's give-up does not
count; silence still ends the match, because the bit rides packets that
must keep arriving.

### 3.6 An old console

A protocol-3 console beside a protocol-4 one hears none of its frames, so it
never forms with it and never takes its START; the new console lists it as
"needs an update" and offers nothing. Two protocol-3 consoles keep forming
as they do today until they update; the release that carries protocol 4 is
the one that stops it.

## 4. The page a Zero serves

**The page plays the same flow.** It runs the shell and the kernel's
`moy_match` over `native/moy_net/moy_link_web.c` (`docs/netplay_v1.md` §5),
so the sheet, Nearby, both lobbies, the invitation, the end card and the
pause menu are the console's pages on the browser's screen, and the page is
a lobby member as a console is. Its name in a list is its board's console
name.

**What the C3 and the XIAO relay:** every frame, both ways, unchanged —
beacons, lobby frames, invitations, START, inputs and a Download Play's
beam — plus each received frame's RSSI, which the link channel's record
gains (`native/moy_net/moy_live.h`), so the page draws
signal. The board keeps no lobby state of its own; a C3's room stays the
relay's ring (`firmware/esp32c3_zero/README.md`).

- **A page that closes ends its part.** Its socket's drop takes the radio
  down (§5 of netplay_v1); the page says CLOSE or LEAVE on `pagehide` where
  the browser lets it, and otherwise its peers' `MOY_MATCH_PEER_TTL_MS` ends
  it for them.
- **An invitation to a Zero** is asked on its page while one is connected.
  With none, its radio service, where it runs, declines it as it declines a
  beam (`docs/os_2026-11/between_apps.md` §6), so a Zero never joins on its
  own; with the radio down nothing is heard at all.
- **Download Play into a page** lands where the page's carts live: on a
  board's origin that is the board's store (`.claude/rules/web.md`, two web
  modes), written through the socket as any of the page's writes; the beam's
  ring is the page's, so the board's memory does not grow with the cart.
- **Same screen on the page** follows §5: two button sources in the browser.

## 5. Same screen

**The source that chose SAME SCREEN is player one, and the other connected
button source is player two, for that run only.** It is #26's source model,
as LOCAL 2P is (`docs/netplay_v1.md` §6): a source carrying a player is that
player, `players()` answers 2, and no radio comes up. The honesty rules
stand: the row is grey where the second source does not exist, and a source
that disconnects mid-run gives its slot back and takes it again when it
returns.

**Settings → 2 PLAYERS goes** (§7, decision 3): the sheet asks each time,
per run, so no console-wide switch is left for a cart to inherit.

| board | player one's buttons | SAME SCREEN is live when |
|---|---|---|
| T-Deck | its keyboard | a paired Bluetooth keyboard is connected (`ws.toggles.second_keyboard()` today) |
| M5Stack CoreS3 SE | its Gamepad face, where fitted | the face is fitted and a Bluetooth keyboard is connected |
| Waveshare P4, Guition P4, Elecrow P4, Guition S3 (touch desks) | the one Bluetooth keyboard | the input task holds a second button source, which none of them does: the row is grey ("Needs two controllers") |
| the page a Zero serves | its keyboard, on-screen pad or a gamepad | two of those are live (a keyboard and a gamepad, or two gamepads) |

A Bluetooth gamepad counts wherever the input task takes one; the BLE task
takes keyboards only (`native/moy_input/moy_ble_task.c`), so a gamepad there
is absence, not a setting.

Same screen and nearby do not combine (three or four players on two
consoles): the lockstep session has two slots.

## 6. What changes in today's code

**Removed: forming by itself.**

- `native/moy_play/moy_match.c`: `maybe_match`'s pairing attempt on the
  beacon tick, `moy_match_offer` / `moy_match_offer_seeded` and
  `moy_match_candidate`'s same-title search, `on_join`'s host-and-re-run, and
  `on_start` re-running a cart already open (`ask` from a START).
- `runtime/run/player.py`: `Player.start` arming the radio and offering on
  every multiplayer cart's start (`link.announce(…, 1)`, `link.offer`); it
  takes the sheet's plan instead (1, same screen, or the session START
  built), and the adoption guards for re-runs in place go with the re-runs.
- `runtime/run/players.py`: `EspNowLink.offer`, `candidate`,
  `launch_cart`'s re-run in place; `announce` becomes the beacon's state.
- `tools/radio_room.py` and its uses in `tests/on_glass.py` and
  `tools/perf_pass.py`: a solo run of a multiplayer seed meets nobody.
- Settings → 2 PLAYERS: `console_settings.set_two_player`, the `two_player`
  row in `runtime/system/settings_rows.py` and
  `runtime/system/settings_layer.py`, and its key in
  `runtime/carts/moy_sync.py`.

**Added.**

- `native/moy_play/moy_match.c` / `.h`: protocol 4; the lobby (host, close,
  join, leave, ready, roster, back), invitations, the session list a screen
  reads, the paused bit; `native/moy_net/moy_link.c` records RSSI, and so do
  `moy_link_web.c` and the live socket's link channel; the C6 shim passes it
  (`native/p4/moy_c6/espnow_shim_proto.h`).
- `runtime/run/players.py`: the lobby's Python face on `EspNowLink`, beside
  the beam's.
- `+runtime/shell/play_sheet.py`: the Players sheet, Nearby, both lobbies and
  the end card, as toolkit pages. The invitation's question beside the
  beam's in `runtime/shell/shell_cards.py`, with PLAY NEARBY in the system
  group. `runtime/shell/pause_ui.py`: RESTART MATCH (host), BACK TO LOBBY,
  QUIT in a match.
- `runtime/boot/devch_links.py`: dev verbs for a bench to drive the flow
  without hands (`link host`, `link join NAME`, `link start`, and a `run`
  that names its players), so a board pass can play a real match.
- The manifest's `moybyte.players` read where the launch decides to run.
- Docs moved at each phase: `docs/netplay_v1.md` (§2's pairing, §3's exit,
  §4's re-run, §6), `docs/moy_cart_api.md` (Multiplayer's two ways),
  `.claude/rules/netplay.md`.

**The phases.** Each lands alone and leaves the console playable.

- **A. The choice replaces forming.** The sheet with all three rows; 1 PLAYER
  arms no radio; SAME SCREEN by the chooser rule; NEARBY CONSOLE arms the
  radio and forms as today, but only between consoles that both chose it;
  Settings → 2 PLAYERS and `tools/radio_room.py` go. The owner's bug (a
  match that re-formed after a restart) ends here. Pins:
  `+tests/test_play_sheet.py` (rows, greying per board, keys and touch, the
  remembered row), `tests/test_local_two_player.py` (the chooser is player
  one), `tests/test_espnow_link.py` (a 1 Player run never brings the radio
  up; two NEARBY runs still match), the sheet's pixel goldens at 320×240 and
  on a touch desk.
- **B. The lobby on the wire.** Protocol 4 in C: presence and session
  beacons, JOIN / ROSTER / READY / LEAVE / CLOSE / BACK, START bound to a
  lobby, RSSI, the paused bit; the same-cart pairing deleted. Pins:
  `tests/test_espnow_link.py`'s two-console harness over its lossy air (host,
  join, start; leave, close and silence; a START or ROSTER from a non-host
  dropped; a protocol-3 beacon listed and never answered; a pause stalls
  without a give-up and silence still ends it).
- **C. The screens over it.** Nearby, both lobbies, the pause menu's rows,
  the end card, the dev verbs. Pins: `+tests/test_play_sheet.py` grown to the
  whole flow on two host consoles; an on-glass hosted match between two
  boards in `tests/on_glass.py` driven by the dev verbs; goldens.
- **D. Invitations.** INVITE and the OS question, the flood rules shared with
  beaming's, BUSY in a match, presence from the always-on radio service.
  Needs #350 phase 1 (the service) and 2b (beaming's question). Pins: the
  backoff and the per-minute cap over forged addresses, a block kept across
  a restart, an invitation during a match answered BUSY.
- **E. Download Play.** JOIN's needs-cart, the host's beam to its guest on the
  reliable lane (#350 phase 2), the first-run ask before ready, a version
  mismatch taken as an update, PLAY NEARBY. Pins: `tests/test_link_beam.py`
  (a lobby beam, then START; a guest that says NO at the first-run ask
  leaves; a stop from either side).
- **F. The page through a Zero.** The relay's RSSI, CLOSE on `pagehide`, an
  invitation to a Zero with no page declined. Pins:
  `tests/test_web_link_e2e.py` and `tests/test_live_link.py`.

## 7. Open decisions for the owner

1. **A Download Play cart stays on the shelf, or goes after the match.**
   Recommended: it stays, as a beamed cart does (one way in, with its
   first-run ask), and the shelf's remove takes it away. A temporary copy
   would be a second install path to keep honest.
2. **Whether an idle console can be invited.** An invitation needs an
   address, so a console must say it is there while it does nothing
   (presence, §3.2). Recommended: visible by default while the radio
   service runs, with Settings → Nearby: Hidden; the flood rules and BLOCK
   already bound what visibility costs. The other way, only consoles with a
   Nearby screen open can be invited, which is close to joining.
3. **Settings → 2 PLAYERS goes.** Recommended: remove it; the sheet asks per
   run, so a console-wide switch only lets a forgotten setting hand player
   two to the next cart.
4. **RESTART in a match.** Recommended: the host's RESTART MATCH restarts
   both consoles from frame zero, and a guest has no restart (BACK TO LOBBY
   is the guest's way back). The other way, any restart ends the match as
   it does today, and the rematch is BACK TO LOBBY then START.
