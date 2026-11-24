-- Moy Mesh's window: the conversations on the LoRa radio, Meshtastic's
-- channels and direct messages, over the service (service.lua) that holds
-- the radio and keeps running when the window closes. Its contract with the
-- service is service.lua's header (the prefs it keeps, the messages both
-- ways); the setup and the channel links are mesh.lua's.
--
-- The window is a UI tree app (the moybyte.uitree extension): its pages
-- describe, the engine lays them out on every board, moves focus and takes
-- the way back. The handlers shape what the service keeps into the state the
-- pages read (reload), and the service's news reaches them as hooks.
--
-- THE PAGES, a stack the bar's way back pops:
--   home      every conversation: the channels, the replaced channels kept
--             read-only, then the direct threads newest first; then Nodes
--             and Radio
--   thread    one conversation: its channel row (a direct thread's header),
--             the history (bubbles on a following scroll), the field and its
--             send key; a bubble's details hang in a popover, a cut
--             message's are the message page
--   message   a cut message whole, and how it was heard
--   nodes     the nodes heard, newest first: a row opens its direct thread
--   radio     This node (the names), Mesh (preset, region), Channels
--   region, preset   the choices, the current one checked; a preset asks
--   channel   a channel's name and key, its link, its removal
--   replaced  a replaced channel, kept read-only, and its removal
--   add       a channel from a link (typed, pasted, or offered from the
--             console's clipboard) or by name
--   link      what a link sets, before it is applied

ui.app("Moy Mesh", { icon = "bubble" })

PLACES = {
  EU_868 = "Europe", EU_433 = "Europe 433", US = "United States", ANZ = "Australia, NZ",
  ANZ_433 = "Australia, NZ 433", CN = "China", JP = "Japan", RU = "Russia", KR = "Korea",
  TW = "Taiwan", IN = "India", NZ_865 = "New Zealand 865", TH = "Thailand",
  UA_433 = "Ukraine 433", UA_868 = "Ukraine 868", MY_433 = "Malaysia 433",
  MY_919 = "Malaysia 919", SG_923 = "Singapore", PH_433 = "Philippines 433",
  PH_868 = "Philippines 868", PH_915 = "Philippines 915", KZ_433 = "Kazakhstan 433",
  KZ_863 = "Kazakhstan 863", NP_865 = "Nepal", BR_902 = "Brazil",
}
HINTS = {
  LONG_FAST = "far \u{b7} default", LONG_MODERATE = "farther, slower",
  LONG_SLOW = "farthest, slowest", LONG_TURBO = "far, quicker",
  MEDIUM_SLOW = "middle, steadier", MEDIUM_FAST = "middle, quick",
  SHORT_SLOW = "short range", SHORT_FAST = "fast, shorter range",
  SHORT_TURBO = "fastest, shortest",
}
-- LoRa's demodulation floor by spreading factor (dB), for the signal's bars
FLOOR = { [7] = -7.5, [8] = -10, [9] = -12.5, [10] = -15, [11] = -17.5, [12] = -20 }
ASK_AGAIN = 60                  -- seconds before Ask for their key returns
TEXT_MAX = 200
LINK_MAX = 255
KEY_ROWS = { { k = "default", label = "Default key", value = "" }, { k = "none", label = "No key", value = "" },
             { k = "random", label = "Random key", value = "\u{203a}" },
             { k = "paste", label = "Paste a key", value = "\u{203a}" } }

log, nodes, threads, order = {}, {}, {}, {}
setup_now = nil
me = ""
now, zone, synced = 0, 0, false
key = "ch0"                     -- the thread the thread page shows
drafts = {}                     -- a thread's unsent text, by its key
ci = 0                          -- the channel the channel page shows (from 0)
old = ""                        -- the replaced channel the replaced page shows
prev = nil                      -- the link the link page shows (url_parse's)

local STATE = { "sending", "sent", "failed", "delivered", { init = "sent" } }
local s = ui.state {
  -- home
  convs = ui.model { key = "k", k = "", name = "", sub = "", age = "", icon = "", count = "", tag = "", mark = "" },
  heard = 0, radio_line = "",
  -- nodes
  heard_nodes = ui.model { key = "id", id = "", label = "", age = "", bars = ui.opt(0) },
  -- the thread
  t = ui.record {
    kind = ui.enum("ch", "dm", "old", { init = "ch" }), name = "", label = "", short = "", tag = "", icon = "",
    first = "", first_icon = "", empty = "", empty2 = "", hint = "",
    keystate = ui.opt(ui.enum("known", "none", "changed", "waiting", { init = "known" })),
    bars = ui.opt(0),
  },
  msgs = ui.model {
    key = "i", i = "", kind = ui.enum("day", "msg", "failed", { init = "msg" }), text = "",
    n = ui.opt(0), side = ui.opt(ui.enum("in", "out", { init = "in" })), head = ui.opt(""), bars = ui.opt(0),
    state = ui.opt(ui.enum(table.unpack(STATE))),
  },
  draft = "",
  pick = ui.opt(ui.record {
    i = 0, dir = ui.enum("in", "out", { init = "in" }), status = "", who = ui.opt(""), name = ui.opt(""),
    rssi = ui.opt(0), snr = ui.opt(0.0), bars = ui.opt(0), failed = false,
  }),
  asked = false, asked_line = "",
  msg = ui.opt(ui.row_of("msgs")),
  -- the radio
  long = "", short = "", console = "", auto = "", me = "",
  preset = "", region = "",
  chans = ui.model { key = "i", i = "", name = "", kind = "" },
  regions = ui.model { key = "i", i = "", place = "", on = false },
  can_add = false,
  -- the preset
  presets = ui.model { key = "k", k = "", title = "", hint = "", on = false },
  preset_k = "", switch_to = "", ask_title = "",
  -- a channel
  ch = ui.record { title = "", hint = "", role = "", primary = false },
  ch_name = "", edited = false,
  keys = ui.model { key = "k", k = "", label = "", value = "", on = false },
  key_k = "", open_keys = false, pasting = false, paste = "", bad_key = false, copied = false,
  removing = false,
  -- add a channel
  url = "", new_name = "", bad = "", clip = false,
  -- a link
  lk = ui.record { preset = "", region = "", slot = "", hops = "", l1 = "", l2 = "", l3 = "" },
  lk_chans = ui.model { key = "i", i = "", line = "" },
  lk_warns = ui.model { key = "i", i = "", text = "" },
  more = false,
}
ui.derive("first_line", { cond = "t.first && t.keystate!=waiting && (msgs || t.keystate=changed)" })
ui.derive("readonly", { cond = "t.kind=old || (t.kind=dm && (t.keystate=waiting || t.keystate=changed))" })
ui.labels("STATUS", { sending = "Sending\u{2026}", sent = "Sending\u{2026}", failed = "Not sent", delivered = "" })
ui.labels("KEYSTATE", { known = "Encrypted", none = "Not private", changed = "Key changed",
                        waiting = "Waiting for key" })
ui.labels("KEYICON", { known = "lock", waiting = "key", none = "warn", changed = "warn" })

-- -- what the service keeps, read ----------------------------------------------

local function upper_id(id)
  return "!" .. id:sub(2):upper()
end

function short_id(id)
  return id:sub(-4):upper()
end

function name_of(id)
  local n = nodes[id]
  if n and type(n.long) == "string" and n.long ~= "" then
    return n.long
  end
  return short_id(id)
end

-- How a node's key stands: "known", "none" (its User came with none),
-- "waiting" (no User heard), "changed" (it announced another).
function key_state(id)
  local n = nodes[id]
  if n == nil or n.long == nil then
    return n and n.key and "known" or "waiting"
  end
  if n.key_new then
    return "changed"
  end
  return n.key and "known" or "none"
end

function bars(rssi, snr)
  if rssi == nil then
    return nil
  end
  local r = rssi >= -100 and 4 or rssi >= -110 and 3 or rssi >= -120 and 2
            or rssi > -130 and 1 or 0
  local m = modem(setup_now.region, setup_now.preset)
  local q_ = (snr or 0) + (-17.5 - (FLOOR[m.sf] or -17.5))
  local q = q_ >= 5 and 4 or q_ >= 0 and 3 or q_ >= -7 and 2 or q_ >= -15 and 1 or 0
  return math.min(r, q)
end

function age(t)
  if type(t) ~= "number" then
    return ""
  end
  local d = now - t
  if d < 60 then
    return "now"
  elseif d < 3600 then
    return string.format("%d min", d // 60)
  elseif d < 86400 then
    return string.format("%d h", d // 3600)
  end
  return string.format("%d d", d // 86400)
end

local MONTHS = { "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
                 "Nov", "Dec" }
local DAYS = { "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun" }

-- The local day `t` falls on, counted from 1970-01-01.
local function day_of(t)
  return (t + zone) // 86400
end

-- A day's head: "Today", "Yesterday", else "Mon 9 Nov".
function day_head(t)
  local d, today = day_of(t), day_of(now)
  if d == today then
    return "Today"
  elseif d == today - 1 then
    return "Yesterday"
  end
  -- the civil date of day d (Howard Hinnant's days_from_civil, inverted)
  local z = d + 719468
  local era = z // 146097
  local doe = z - era * 146097
  local yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
  local doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
  local mp = (5 * doy + 2) // 153
  local dd = doy - (153 * mp + 2) // 5 + 1
  local mm = mp < 10 and mp + 3 or mp - 9
  return string.format("%s %d %s", DAYS[(d + 3) % 7 + 1], dd, MONTHS[mm])
end

local function public(c)
  local psk = c.psk
  return psk == "" or psk == DEFAULT_PSK or psk == "AA==" or (#psk <= 4 and psk ~= "")
end

function key_kind(c, i)
  if c.psk == "" and i > 1 then
    return "Primary's key"
  elseif c.psk == "AA==" then
    return "No key"
  elseif #c.psk <= 4 then
    return "Default key"
  end
  local n = #(b64_bytes(c.psk) or "")
  return n == 16 and "128-bit key" or n == 32 and "256-bit key" or "Key"
end

local function preset_title(st)
  local _, p = modem(st.region, st.preset)
  return MODEMS[p].title
end

local function console_name()
  local ok, n = pcall(moybyte.name)
  return ok and type(n) == "string" and n or ""
end

local function failed(r)
  return r.failed or r.state == "failed"
end

local function thread_of(k)
  local t = threads[k]
  if t == nil then
    t = { key = k, msgs = {}, last = 0, unread = 0 }
    threads[k] = t
  end
  return t
end

-- -- shaping: what the service keeps, into the state the pages read --------------

-- The first line of a thread: who can read it.
local function first_line(t)
  if t.kind == "dm" then
    if key_state(t.peer) == "none" then
      local c = setup_now.channels[(nodes[t.peer] and nodes[t.peer].ch or 0) + 1]
      return "warn", "Not private: others on " .. (c and channel_name(setup_now, 1) or "the channel")
        .. " can read this."
    end
    return "lock", "Only " .. name_of(t.peer) .. "'s radio can read these."
  end
  if t.public then
    return "bubble", "Public: anyone who knows the name can read it."
  end
  return "", ""
end

local function preview(t)
  local m = t.msgs[#t.msgs]
  if m == nil then
    if t.kind == "dm" and key_state(t.peer) == "waiting" then
      return "Waiting for their key"
    end
    return "No messages yet"
  end
  local who = m.r.from == "" and "You: " or (t.kind == "dm" and "" or name_of(m.r.from) .. ": ")
  return who .. (m.r.text or "")
end

local function header(t)
  local first_icon, first = first_line(t)
  if t.kind ~= "dm" then
    local label = t.name
    if t.kind == "ch" and t.name ~= MODEMS[setup_now.preset].title then
      label = t.name .. " \u{b7} " .. preset_title(setup_now)
    end
    local h = { kind = t.kind, name = t.name, short = "", label = label, first = first, first_icon = first_icon,
                tag = t.kind == "old" and "Read-only" or t.public and "Public" or "",
                icon = (t.kind == "old" or t.public) and "" or "lock",
                empty = "Messages on " .. t.name .. " show up here.",
                empty2 = t.public and "Public: anyone who knows the name can read it." or "",
                hint = "Message " .. t.name }
    if t.kind == "old" then
      h.hint = "Replaced by " .. threads.ch0.name .. " \u{b7} read-only"
    end
    return h
  end
  local k, who, n = key_state(t.peer), name_of(t.peer), nodes[t.peer] or {}
  return { kind = "dm", name = who, short = short_id(t.peer), keystate = k, bars = bars(n.rssi, n.snr),
           label = who == short_id(t.peer) and who or who .. "  " .. short_id(t.peer), tag = "", icon = "",
           first = first, first_icon = first_icon, empty = first, empty2 = "",
           hint = k == "waiting" and "Waiting for their key" or k == "changed" and "Accept the new key to write"
                  or "Message " .. who }
end

local function msg_row(t, m)
  local r = m.r
  local row = { i = "m" .. m.i, n = m.i, kind = r.from == "" and failed(r) and "failed" or "msg", text = r.text or "",
                side = r.from == "" and "out" or "in" }
  if r.from == "" then
    if r.state == "sending" or r.state == "sent" then row.state = r.state end
  else
    if t.kind ~= "dm" then row.head = name_of(r.from) end
    row.bars = bars(r.rssi, r.snr)
  end
  return row
end

-- The thread page's state, for thread `key`.
local function shape_thread()
  local t = threads[key]
  if t == nil then
    return
  end
  s.t = header(t)
  local rows, day = {}, nil
  local many = synced and #t.msgs > 0 and day_of(t.msgs[1].r.t or now) ~= day_of(now)
  for _, m in ipairs(t.msgs) do
    if many and m.r.t and day_of(m.r.t) ~= day then
      day = day_of(m.r.t)
      rows[#rows + 1] = { i = "d" .. day, kind = "day", text = day_head(m.r.t) }
    end
    rows[#rows + 1] = msg_row(t, m)
  end
  s.msgs:set(rows)
  local n = t.kind == "dm" and nodes[t.peer]
  s.asked = n and n.asked ~= nil and now - n.asked < ASK_AGAIN or false
  s.asked_line = s.asked and "Asked \u{b7} " .. (now - n.asked < 60 and "just now" or age(n.asked) .. " ago") or ""
end

local function shape_home()
  local rows = {}
  for i, t in ipairs(order) do
    local tag, mark = "", ""
    if t.kind == "old" then
      tag = "Read-only"
    elseif t.kind == "ch" then
      tag, mark = t.public and "Public" or "", t.public and "" or "lock"
    else
      mark = key_state(t.peer) == "known" and "lock" or ""
    end
    rows[i] = { k = t.key, name = t.name, sub = preview(t), age = t.last > 0 and age(t.last) or "",
                icon = t.kind == "dm" and "@" .. t.name or "bubble",
                count = t.unread > 0 and tostring(t.unread) or "", tag = tag, mark = mark }
  end
  s.convs:set(rows)
  local ids = {}
  for id in pairs(nodes) do ids[#ids + 1] = id end
  table.sort(ids, function(a, b) return (nodes[a].heard or 0) > (nodes[b].heard or 0) end)
  rows = {}
  for i, id in ipairs(ids) do
    local n, who = nodes[id], name_of(id)
    rows[i] = { id = id, label = who == short_id(id) and who or who .. "  " .. short_id(id), age = age(n.heard),
                bars = bars(n.rssi, n.snr) }
  end
  s.heard_nodes:set(rows)
  s.heard = #ids
  s.radio_line = preset_title(setup_now) .. ", " .. setup_now.region
end

local function shape_radio()
  local st = setup_now
  local own = prefs.get("long_name") or ""
  own = own ~= "" and own or console_name()
  s.console = console_name()
  s.long = own
  -- the service's default (service.lua's short_default)
  s.auto = (own == "" or own:sub(1, 7):lower() == "moybyte") and me:sub(-4) or clip(own, 4)
  local short = prefs.get("short_name") or ""
  s.short = short ~= "" and short or s.auto
  s.me = me ~= "" and upper_id(me) or ""
  s.preset, s.region = preset_title(st), st.region
  local rows = {}
  for i, c in ipairs(st.channels) do
    rows[i] = { i = "c" .. i, name = channel_name(st, i), kind = i == 1 and "Primary" or key_kind(c, i) }
  end
  s.chans:set(rows)
  s.can_add = #st.channels < CHANNELS_MAX
end

local function shape_channel()
  local c = setup_now.channels[ci + 1]
  if c == nil then
    return
  end
  local kind = key_kind(c, ci + 1)
  s.ch = { title = channel_name(setup_now, ci + 1), hint = MODEMS[setup_now.preset].title,
           role = ci == 0 and "Primary" or "Secondary", primary = ci == 0 }
  s.ch_name = c.name
  s.key_k = kind == "Default key" and "default" or kind == "No key" and "none" or "random"
  local rows = {}
  for i, r in ipairs(KEY_ROWS) do
    rows[i] = { k = r.k, label = r.label, value = r.value, on = r.k == s.key_k }
  end
  s.keys:set(rows)
end

function _reload()
  local l = prefs.get("log")
  log = type(l) == "table" and l or {}
  local n = prefs.get("nodes")
  nodes = type(n) == "table" and n or {}
  setup_now = setup()
  local id = prefs.get("node")
  me = type(id) == "string" and id or ""
  now, zone, synced = wall()
  local seen = prefs.get("seen")
  seen = type(seen) == "table" and seen or {}
  threads, order = {}, {}
  for i = 1, #setup_now.channels do
    local t = thread_of("ch" .. (i - 1))
    t.kind, t.ci, t.name = "ch", i - 1, channel_name(setup_now, i)
    t.public = public(setup_now.channels[i])
    order[#order + 1] = t
  end
  local olds, dms = {}, {}
  for i, r in ipairs(log) do
    local t
    if r.dm then
      t = thread_of(r.dm)
      if t.kind == nil then
        t.kind, t.peer = "dm", r.dm
        dms[#dms + 1] = t
      end
    elseif r.old then
      t = thread_of("old:" .. r.old)
      if t.kind == nil then
        t.kind, t.name, t.old = "old", r.old, true
        olds[#olds + 1] = t
      end
    else
      t = threads["ch" .. (r.ch or 0)]
    end
    if t then
      t.msgs[#t.msgs + 1] = { i = i, r = r }
      t.last = math.max(t.last, r.t or 0)
      if r.from ~= "" and (r.t or 0) > (seen[t.key] or 0) then
        t.unread = t.unread + 1
      end
    end
  end
  -- a direct thread opened from a node with nothing in it yet
  if key:sub(1, 1) == "!" and threads[key] == nil then
    local t = thread_of(key)
    t.kind, t.peer = "dm", key
    dms[#dms + 1] = t
  end
  table.sort(dms, function(a, b) return a.last > b.last end)
  for _, t in ipairs(olds) do order[#order + 1] = t end
  for _, t in ipairs(dms) do
    t.name = name_of(t.peer)
    order[#order + 1] = t
  end
  shape_home()
  shape_thread()
  shape_radio()
  shape_channel()
end

-- Thread `key` read: its unread count goes.
local function mark_seen()
  local t = threads[key]
  if t and t.unread > 0 then
    local seen = prefs.get("seen")
    seen = type(seen) == "table" and seen or {}
    seen[key] = t.last
    prefs.set("seen", seen)
    t.unread = 0
    shape_home()
  end
end

-- Whether focus is on the thread page (a key only that page has).
local THREAD_KEYS = { chan = true, draft = true, send = true, ask = true, notnow = true, accept = true,
                      resend = true, delete = true, message_sender = true }
local function on_thread()
  local f = ui.sys.focus
  return THREAD_KEYS[f] or f:find("^[md]%d+/") ~= nil
end

local function news()
  _reload()
  if on_thread() then mark_seen() end
end

local function open_thread(k)
  drafts[key] = s.draft
  key = k
  s.draft = drafts[k] or ""
  s.pick = nil
  _reload()
  mark_seen()
  ui.push("thread")
end

local function retune(st)
  setup_save(st)
  moybyte.send(ME, "retune")
  _reload()
end

-- -- the service's news, and the window's start ------------------------------------

function _init()
  moybyte.on("heard", function() ui.post("news") end)
  moybyte.on("nodes", function() ui.post("news") end)
  moybyte.every(30000, function() ui.post("tick") end)
  moybyte.service_start()
end

ui.hook("opened", function() _reload() end)
ui.hook("news", news)
ui.hook("tick", function() _reload() end)

-- -- the home and the nodes -----------------------------------------------------

ui.action("open", "Open", function(row) open_thread(row.k) end, { takes = "row", hint = "Open" })
ui.action("nodes", "Nodes", function() ui.push("nodes") end, { hint = "Open" })
ui.action("radio", "Radio", function() ui.push("radio") end, { hint = "Open" })
ui.action("message_node", "Message", function(row) open_thread(row.id) end, { takes = "row", hint = "Message" })

-- -- the thread -----------------------------------------------------------------------

-- The send target the service takes: a channel's index or a node's id.
local function target()
  local t = threads[key]
  return t.kind == "dm" and t.peer or t.ci
end

local function details(row)
  local r = log[row.n]
  s.msg = row
  if r.from ~= "" then
    local who = name_of(r.from)
    s.pick = { i = row.n, dir = "in", status = "", failed = false, name = who, rssi = r.rssi or 0,
               snr = (r.snr or 0) + 0.0, bars = bars(r.rssi, r.snr) or 0,
               who = who == short_id(r.from) and upper_id(r.from) or who .. " \u{b7} " .. upper_id(r.from) }
  else
    local dm = threads[key].kind == "dm"
    if failed(r) then ui.focus("resend") end
    s.pick = { i = row.n, dir = "out", failed = failed(r),
               status = failed(r) and "Not sent" or r.state == "delivered" and "Delivered"
                        or (r.state == "sending" or r.state == "sent") and dm and "Sending" or "Sent" }
  end
end

ui.action("send", "Send", function()
  if s.draft ~= "" then moybyte.send(ME, "send", s.draft, target()) end
  s.draft = ""
end, { icon = "arrow_up", when = "!readonly", off = "grey" })
ui.action("resend", "Send again", function(row)
  moybyte.send(ME, "act", "resend", row.n, log[row.n].text)
  s.pick = nil
end, { row = "msg", off = "hide" })
ui.action("details", "Details", details, { takes = "row", keys = { "role:more" } })
ui.action("open_message", "Open", function(row) details(row); ui.push("message", row) end, { takes = "row" })
ui.action("delete", "Delete", function(row)
  moybyte.send(ME, "act", "delete", row.n, log[row.n].text)
  s.pick = nil
end, { row = "msg", off = "hide" })
ui.action("close_details", "Close", function() s.pick = nil end)
ui.action("ask", "Ask for their key", function()
  moybyte.send(ME, "act", "ask", key)
end, { hint = "Ask for key" })
ui.action("accept", "Accept", function() moybyte.send(ME, "act", "accept", key) end)
ui.action("notnow", "Not now", function() ui.pop() end)
ui.action("chan", "Channel", function()
  local t = threads[key]
  if t.kind == "old" then
    old = t.name
    s.ch = { title = t.name, hint = "", role = "", primary = false }
    s.removing = false
    ui.push("replaced")
  else
    ci = t.ci
    s.edited, s.pasting, s.paste, s.bad_key, s.copied, s.removing, s.open_keys = false, false, "", false, false, false, false
    shape_channel()
    ui.push("channel")
  end
end, { hint = "Channel" })
ui.action("message_sender", "Message", function()
  local from = log[s.pick.i].from
  s.pick = nil
  ui.pop()
  open_thread(from)
end)

-- -- the radio's pages --------------------------------------------------------------

ui.action("save_long", "Save", function()
  -- the console's own name, or none, is the console's: it follows it
  prefs.set("long_name", s.long ~= console_name() and s.long or "")
  moybyte.send(ME, "retune")
  _reload()
end)
ui.action("save_short", "Save", function()
  prefs.set("short_name", s.short ~= s.auto and s.short or "")
  moybyte.send(ME, "retune")
  _reload()
end)
ui.action("open_preset", "Preset", function()
  local _, p = modem(setup_now.region, setup_now.preset)
  local rows = {}
  for i, k in ipairs(PRESETS) do
    rows[i] = { k = k, title = MODEMS[k].title, hint = HINTS[k] or "", on = k == p }
  end
  s.presets:set(rows)
  s.preset_k, s.switch_to = p, ""
  ui.push("preset")
end, { hint = "Edit" })
ui.action("open_region", "Region", function()
  local rows = {}
  for i, r in ipairs(REGIONS) do rows[i] = { i = r, place = PLACES[r] or "", on = r == setup_now.region } end
  s.regions:set(rows)
  ui.push("region")
end, { hint = "Edit" })
ui.action("channel", "Channel", function(row)
  ci = tonumber(row.i:sub(2)) - 1
  s.edited, s.pasting, s.paste, s.bad_key, s.copied, s.removing, s.open_keys = false, false, "", false, false, false, false
  shape_channel()
  ui.push("channel")
end, { takes = "row", hint = "Edit" })
ui.action("add", "Add channel", function()
  local url = clip_link()
  s.clip, s.url, s.new_name, s.bad = url ~= nil, "", "", ""
  clipped = url
  ui.push("add")
end, { hint = "Edit" })
ui.action("pick_region", "Choose", function(row)
  local st = setup()
  st.region = row.i
  retune(st)
end, { takes = "row" })
ui.action("pick_preset", "Choose", function(row)
  if row.k ~= s.preset_k then
    s.switch_to, s.ask_title = row.k, row.title
  end
end, { takes = "row" })
ui.action("cancel_switch", "Cancel", function() s.switch_to = "" end)
ui.action("switch", "Switch", function()
  local st = setup()
  st.preset = s.switch_to
  s.preset_k, s.switch_to = st.preset, ""
  retune(st)
end)

-- -- a channel ---------------------------------------------------------------------------

ui.action("save_name", "Save", function()
  local st = setup()
  local c = st.channels[ci + 1]
  if c and s.ch_name ~= c.name then
    c.name = s.ch_name
    s.edited = true
    retune(st)
  end
end)
ui.action("pick_key", "Choose", function(row)
  local st = setup()
  local c = st.channels[ci + 1]
  if row.k == "default" then
    c.psk = DEFAULT_PSK
    s.edited = true
    retune(st)
  elseif row.k == "none" then
    c.psk = "AA=="
    s.edited = true
    retune(st)
  elseif row.k == "random" then
    s.open_keys = true
  else
    s.pasting, s.paste, s.bad_key = true, "", false
  end
end, { takes = "row" })
local function random_key(n)
  moybyte.send(ME, "act", "key", ci, n)
  s.open_keys, s.edited = false, true
end
ui.action("key128", "128-bit key", function() random_key(16) end, { icon = "key" })
ui.action("key256", "256-bit key", function() random_key(32) end, { icon = "key" })
ui.action("close_keys", "Close", function() s.open_keys = false end)
ui.action("save_key", "Save", function()
  local raw = b64_bytes(s.paste)
  if raw and (#raw == 16 or #raw == 32) then
    local st = setup()
    st.channels[ci + 1].psk = b64(raw)
    s.pasting, s.paste, s.bad_key, s.edited = false, "", false, true
    retune(st)
  else
    s.bad_key = true
  end
end)
ui.action("copy", "Copy channel link", function()
  local st = setup()
  local one = { region = st.region, preset = st.preset, slot = st.slot, hops = st.hops,
                channels = { st.channels[ci + 1] } }
  clipboard.put_text(url_make(one))
  s.copied = true
end)
ui.action("remove", "Remove channel", function() s.removing = true end, { hint = "Remove" })
ui.action("cancel_remove", "Cancel", function() s.removing = false end)
ui.action("remove_it", "Remove", function()
  local st = setup()
  table.remove(st.channels, ci + 1)
  s.removing = false
  retune(st)
  ui.pop()
end)
ui.action("remove_old", "Remove", function()
  local l = prefs.get("log") or {}
  for i = #l, 1, -1 do
    if l[i].old == old then table.remove(l, i) end
  end
  prefs.set("log", l)
  s.removing = false
  key = "ch0"
  _reload()
  ui.pop()
  ui.pop()
end)

-- -- adding a channel --------------------------------------------------------------------

function clip_link()
  if clipboard == nil then
    return nil
  end
  local ok, k = pcall(clipboard.kind)
  if not ok or k == nil then
    return nil
  end
  local ok2, txt = pcall(clipboard.text)
  if not ok2 or type(txt) ~= "string" then
    return nil
  end
  txt = txt:match("^%s*(.-)%s*$")
  if txt:find("^meshtastic%.org/e/") or txt:find("^https://meshtastic%.org/e/") then
    return txt
  end
  return nil
end

local function from_to(a, b)
  return a == b and a or a .. " to " .. b
end

-- The link page's state, for link `prev`.
local function shape_link()
  local cur = setup()
  local next_s = setup_merge(prev, cur)
  local rows = {}
  for i, c in ipairs(prev.channels) do
    local nm = c.name ~= "" and c.name or MODEMS[next_s.preset].title
    rows[i] = { i = "c" .. i, line = nm .. " \u{b7} " .. (public(c) and "Public" or "Keyed") }
  end
  s.lk_chans:set(rows)
  rows = {}
  for i, wn in ipairs(prev.warnings or {}) do rows[i] = { i = "w" .. i, text = wn } end
  s.lk_warns:set(rows)
  local lines = {}
  if prev.add then
    local n = {}
    for _, c in ipairs(prev.channels) do n[#n + 1] = c.name end
    lines[1] = "Adds " .. table.concat(n, ", ") .. "."
  else
    lines[1] = channel_name(cur, 1) .. " is replaced; its messages stay, read-only."
  end
  if next_s.preset ~= cur.preset then
    lines[#lines + 1] = "You will hear only " .. MODEMS[next_s.preset].title .. " radios."
  end
  if next_s.region ~= cur.region then
    lines[#lines + 1] = "Region is law: set the one you are in."
  end
  s.lk = { preset = from_to(MODEMS[cur.preset].title, MODEMS[next_s.preset].title),
           region = from_to(cur.region, next_s.region), slot = tostring(next_s.slot),
           hops = tostring(next_s.hops), l1 = lines[1] or "", l2 = lines[2] or "", l3 = lines[3] or "" }
  s.more = false
end

local function read_link(url)
  local link = url:find("^https?://") and url or "https://" .. url
  local p, why = url_parse(link)
  if p == nil then
    s.bad = why or "That is not a channel link."
    return
  end
  s.bad = ""
  prev = p
  shape_link()
  ui.push("link")
end

ui.action("read_url", "Read link", function() if s.url ~= "" then read_link(s.url) end end)
ui.action("paste_link", "Paste link", function() read_link(clipped) end, { hint = "Paste" })
local function add_named()
  if s.new_name == "" then
    return
  end
  local st = setup()
  if #st.channels < CHANNELS_MAX then
    st.channels[#st.channels + 1] = { name = s.new_name, psk = DEFAULT_PSK }
    setup_save(st)
    moybyte.send(ME, "act", "key", #st.channels - 1, 32)
    _reload()
    ui.pop()
  end
end
ui.action("add_named", "Add", add_named)
ui.action("cancel_link", "Cancel", function() ui.pop() end)
ui.action("apply", "Apply", function()
  local next_s = setup_merge(prev, setup())
  if not prev.add then
    moybyte.send(ME, "act", "retire")
  end
  setup_save(next_s)
  moybyte.send(ME, "retune")
  key = "ch0"
  _reload()
  ui.pop()
  ui.pop()
  ui.pop()
end)
ui.action("details_link", "Details", function() s.more = not s.more end)

-- -- the pages ---------------------------------------------------------------------------

ui.page("home", function()
  ui.scroll("home", function()
    ui.group("", { look = "card" }, function()
      ui.rows("convs", function()
        ui.link("open", { label = "{.name}", value = "{.age}", sub = "{.sub}", icon = "{.icon}", count = "{.count}",
                          tag = "{.tag}", mark = "{.mark}", focus = true })
      end)
    end)
    ui.group("", { look = "card" }, function()
      ui.link("nodes", { value = "{heard} heard" })
      ui.link("radio", { value = "{radio_line}" })
    end)
  end)
end, { title = "" })

ui.page("thread", function()
  ui.switch("t.kind", {
    dm = function()
      ui.info("{t.label}", { value = "{t.keystate|map KEYSTATE}", icon = "{t.keystate|map KEYICON}",
                             signal = "{t.bars}" })
    end,
    ch = function()
      ui.link("chan", { label = "{t.label}", value = "", tag = "{t.tag}", icon = "{t.icon}" })
    end,
    old = function()
      ui.link("chan", { label = "{t.label}", value = "", tag = "{t.tag}", focus = true })
    end,
  })
  ui.scroll("thread", { follow = true }, function()
    ui.label("{t.first}", { icon = "{t.first_icon}",
                            shown = "first_line" })
    ui.rows("msgs", { by = "kind" }, {
      day = function() ui.label("{.text}") end,
      msg = function()
        ui.bubble("{.text}", { side = "{.side}", head = "{.head}", signal = "{.bars}", status = "{.state|map STATUS}",
                               on = "details", cut = "open_message" })
      end,
      failed = function()
        ui.bubble("{.text}", { side = "out", tone = "failed", status = "Not sent", on = "details" })
      end,
    })
    ui.empty("No messages yet", { icon = "bubble", lines = { "{t.empty}", "{t.empty2}" },
                                  shown = "!msgs && !readonly" })
    ui.empty("Waiting for {t.name}'s key", {
      icon = "key", shown = "t.keystate=waiting",
      lines = { "Only {t.short}'s radio will be able to read it.",
                "{@tall?Its key comes with its name;:Its key comes with its name.}",
                "{@tall?you can write once it's heard.:}" },
    }, function()
      ui.button("ask", { kind = "primary", focus = true, shown = "!asked" })
      ui.label("{asked_line}", { icon = "check", shown = "asked" })
    end)
  end)
  ui.foot(function()
    ui.note({ icon = "warn", lines = { "{t.name}'s key changed.",
                                       "This can mean a reset radio, or someone pretending. Accept the new key?" },
              shown = "t.keystate=changed" })
    ui.row("decide", { shown = "t.keystate=changed" }, function()
      ui.button("notnow", { kind = "primary", focus = true })
      ui.button("accept")
    end)
    ui.row("write", function()
      ui.field("draft", { label = "", max = TEXT_MAX, hint = "{t.hint}", grow = true, focus = "!readonly",
                          on = "send", when = "!readonly", off = "grey" })
      ui.button("send", { label = "", kind = "primary" })
    end)
  end)
  ui.popover("details", { shown = "pick", anchor = "m{pick.i}", w = "{@desk?380:300}", wash = "view",
                          close = "close_details" }, function()
    ui.switch("pick.dir", {
      ["in"] = function()
        ui.info("From", { value = "{pick.who}" })
        ui.info("Signal", { value = "{pick.rssi} dBm \u{b7} SNR {pick.snr|fmt %.1f} dB", signal = "{pick.bars}" })
        ui.button("message_sender", { kind = "primary", label = "Message {pick.name}" })
      end,
      out = function()
        ui.info("{t.kind=dm?To:Channel}", { value = "{t.name}" })
        ui.info("Status", { value = "{pick.status}", tone = "{pick.failed?danger:}" })
        ui.button("delete", { kind = "danger", shown = "pick.failed" })
        ui.button("resend", { kind = "primary", shown = "pick.failed", focus = true })
      end,
    })
  end)
end, { title = "" })

ui.page("message", function()
  ui.scroll("message", function()
    ui.bubble("{msg.text}", { max = 1, lines = 0, head = "{msg.head}", signal = "{msg.bars}" })
    ui.switch("pick.dir", {
      ["in"] = function()
        ui.group("Heard", function()
          ui.info("From", { value = "{pick.who}" })
          ui.info("Signal", { value = "{pick.rssi} dBm", signal = "{pick.bars}" })
          ui.info("SNR", { value = "{pick.snr|fmt %.1f} dB" })
        end)
      end,
      out = function()
        ui.group("Sent", function()
          ui.info("{t.kind=dm?To:Channel}", { value = "{t.name}" })
          ui.info("Status", { value = "{pick.status}", tone = "{pick.failed?danger:}" })
        end)
      end,
    })
  end)
end, { title = "Message", arg = "msg" })

ui.page("nodes", function()
  ui.empty("No nodes heard yet", { icon = "radio", lines = { "A node shows here once its radio is heard." },
                                   shown = "!heard_nodes" })
  ui.scroll("node_list", function()
    ui.group("Heard \u{b7} {heard}", { shown = "heard_nodes" }, function()
      ui.rows("heard_nodes", function()
        ui.link("message_node", { label = "{.label}", value = "{.age}", signal = "{.bars}", focus = true })
      end)
    end)
  end)
end, { title = "Nodes" })

ui.page("radio", function()
  ui.scroll("radio", function()
    ui.group("This node", function()
      ui.field("long", { label = "Name", max = 39, hint = "{console}", commit = true, on = "save_long" })
      ui.field("short", { label = "Short name", max = 4, hint = "{auto}", commit = true, on = "save_short" })
      ui.info("Id", { value = "{me}", shown = "me" })
    end)
    ui.group("Mesh", function()
      ui.link("open_preset", { value = "{preset}", focus = true })
      ui.link("open_region", { value = "{region}" })
    end)
    ui.group("Channels", function()
      ui.rows("chans", function() ui.link("channel", { label = "{.name}", value = "{.kind}" }) end)
      ui.link("add", { icon = "plus", value = "", tone = "value", shown = "can_add" })
    end)
  end)
end, { title = "Radio" })

ui.page("region", function()
  ui.scroll("regions", function()
    ui.group("Region", function()
      ui.rows("regions", { current = "region", check = true }, function()
        ui.link("pick_region", { label = "{.i}", value = "{.place}", focus = ".on" })
      end)
    end)
  end)
end, { title = "Region" })

ui.page("preset", function()
  ui.scroll("presets", function()
    ui.note({ icon = "warn", lines = { "Every radio on a mesh uses one preset.",
                                       "On another one you hear none of them." } })
    ui.group("Preset", function()
      ui.rows("presets", { current = "preset_k", check = true }, function()
        ui.link("pick_preset", { label = "{.title}", value = "{.hint}", focus = ".on" })
      end)
    end)
  end)
  ui.dialog("Switch to {ask_title}?", { buttons = { "cancel_switch", "switch" }, kind = "primary", shown = "switch_to" }, function()
    ui.label("You will hear only radios on {ask_title},")
    ui.label("and only they hear you.")
    ui.label("Your channels and messages stay.")
  end)
end, { title = "Preset" })

ui.page("channel", function()
  ui.scroll("channel", function()
    ui.group("Channel", function()
      ui.field("ch_name", { label = "Name", max = CHANNEL_NAME_MAX, hint = "{ch.hint}", commit = true,
                            on = "save_name" })
      ui.info("Role", { value = "{ch.role}" })
    end)
    ui.note({ icon = "warn", lines = { "Radios that do not have the new name and key no longer read it.",
                                       "Share the channel's link with them." }, shown = "edited" })
    ui.group("Key", function()
      ui.rows("keys", { current = "key_k", check = true }, function()
        ui.link("pick_key", { label = "{.label}", value = "{.value}", focus = ".on" })
      end)
      ui.field("paste", { label = "Key", max = 44, hint = "Base64, 16 or 32 bytes", commit = true, on = "save_key",
                          shown = "pasting" })
      ui.label("That is not a key of 16 or 32 bytes.", { shown = "pasting && bad_key" })
    end)
    ui.label("Anyone who knows the name can read it.", { shown = "key_k!=random" })
    ui.group("Share", function()
      ui.link("copy", { value = "" })
      ui.info("Copied", { value = "", shown = "copied" })
    end)
    ui.button("remove", { kind = "danger", shown = "!ch.primary" })
  end)
  ui.popover("random", { shown = "open_keys", anchor = "random", close = "close_keys" }, function()
    ui.menu("Random key", function()
      ui.item("key128")
      ui.item("key256")
    end)
  end)
  ui.dialog("Remove {ch.title}?", { buttons = { "cancel_remove", "remove_it" }, kind = "danger", shown = "removing" }, function()
    ui.label("Radios on it no longer reach this console.")
  end)
end, { title = "{ch.title}" })

ui.page("replaced", function()
  ui.label("This channel was replaced; its messages stay, read-only.")
  ui.button("remove", { kind = "danger", focus = true })
  ui.dialog("Remove {ch.title}?", { buttons = { "cancel_remove", "remove_old" }, kind = "danger", shown = "removing" }, function()
    ui.label("Its messages go with it.")
  end)
end, { title = "{ch.title}" })

ui.page("add", function()
  ui.scroll("add", function()
    ui.group("From a link", function()
      ui.field("url", { label = "", max = LINK_MAX, hint = "meshtastic.org/e/#\u{2026}", on = "read_url" })
    end)
    ui.label("{bad}", { shown = "bad" })
    ui.note({ icon = "paste", lines = { "Your clipboard holds a channel link." }, shown = "!bad && clip" })
    ui.group("", { look = "card", shown = "!bad && clip" }, function()
      ui.link("paste_link", { icon = "paste", value = "", tone = "value", focus = true })
    end)
    ui.label("Paste or type a meshtastic.org/e/ link.", { shown = "!bad && !clip" })
    ui.group("By name", function()
      ui.field("new_name", { label = "Name", max = CHANNEL_NAME_MAX, hint = "Channel name", on = "add_named" })
      ui.info("Key", { value = "Random key" })
    end)
  end)
  ui.foot({ look = "end" }, function()
    ui.button("add_named", { kind = "{clip?normal:primary}", focus = "!clip" })
  end)
end, { title = "Add channel" })

ui.page("link", function()
  ui.scroll("link", function()
    ui.group("", { look = "card" }, function()
      ui.rows("lk_chans", function() ui.info("Channel", { value = "{.line}" }) end)
      ui.info("Preset", { value = "{lk.preset}" })
      ui.info("Region", { value = "{lk.region}" })
      ui.link("details_link", { value = "" })
      ui.info("Frequency slot", { value = "{lk.slot}", shown = "more" })
      ui.info("Hop limit", { value = "{lk.hops}", shown = "more" })
      ui.rows("lk_warns", { shown = "more" }, function() ui.label("{.text}") end)
    end)
    ui.note({ icon = "warn", lines = { "{lk.l1}", "{lk.l2}", "{lk.l3}" } })
  end)
  ui.foot({ look = "end" }, function()
    ui.button("cancel_link", { focus = true })
    ui.button("apply", { kind = "primary" })
  end)
end, { title = "Channel link" })
