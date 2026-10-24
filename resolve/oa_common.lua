-- Original Accent bridge for DaVinci Resolve (free or Studio). Installed and updated by
-- Original Accent; changes here are overwritten. Each menu item is one of these files.
-- The scripts and the app swap files in %LOCALAPPDATA%\OriginalAccent\resolve.
local OA_DIR = os.getenv("OA_BRIDGE_DIR") or ((os.getenv("LOCALAPPDATA") or "") .. "\\OriginalAccent\\resolve\\")

local function oa_resolve()
  if resolve then return resolve end
  if Resolve then local ok, r = pcall(Resolve); if ok and r then return r end end
  if bmd and bmd.scriptapp then return bmd.scriptapp("Resolve") end
  return nil
end

local function oa_fail(msg) error({ oa = msg }, 0) end

local function oa_esc(s)
  local map = { ['"'] = '\\"', ['\\'] = '\\\\', ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t' }
  local out = tostring(s):gsub('[%c"\\]', function(c) return map[c] or string.format("\\u%04x", c:byte()) end)
  return '"' .. out .. '"'
end

local function oa_json(v)
  local t = type(v)
  if t == "table" then
    local n, keys = 0, 0
    for k in pairs(v) do keys = keys + 1; if type(k) == "number" then n = math.max(n, k) end end
    if keys == 0 or n == keys then
      local parts = {}
      for i = 1, n do parts[#parts + 1] = oa_json(v[i]) end
      return "[" .. table.concat(parts, ",") .. "]"
    end
    local parts = {}
    for k, x in pairs(v) do parts[#parts + 1] = oa_esc(k) .. ":" .. oa_json(x) end
    return "{" .. table.concat(parts, ",") .. "}"
  elseif t == "string" then return oa_esc(v)
  elseif t == "number" then return tostring(v)
  elseif t == "boolean" then return v and "true" or "false"
  end
  return "null"
end

local function oa_write(name, msg)
  local final, part = OA_DIR .. name, OA_DIR .. name .. ".part"
  local f = io.open(part, "w")
  if not f then
    print("Original Accent: can't write to " .. OA_DIR .. ". Open Original Accent once, then try again.")
    return false
  end
  f:write(oa_json(msg)); f:close()
  os.remove(final); os.rename(part, final)
  return true
end

local function oa_context(need_timeline)
  local r = oa_resolve()
  if not r then oa_fail("This script has to be run from inside DaVinci Resolve (Workspace > Scripts).") end
  local pm = r:GetProjectManager()
  local project = pm and pm:GetCurrentProject()
  if not project then oa_fail("Resolve has no project open.") end
  local tl = project:GetCurrentTimeline()
  if need_timeline and not tl then oa_fail("Open a timeline in Resolve first.") end
  return r, project, tl
end

local function oa_fps(project, tl)
  local v = (tl and tl:GetSetting("timelineFrameRate")) or project:GetSetting("timelineFrameRate") or "24"
  return tonumber(string.match(tostring(v), "[%d%.]+")) or 24
end

local function oa_df(project, tl)
  local v = tostring((tl and tl:GetSetting("timelineDropFrameTimecode")) or project:GetSetting("timelineDropFrameTimecode") or "0")
  return v == "1" or v == "true" or v == "True"
end

local function oa_tc_to_frames(tc, fps)
  local df = string.find(tc, ";") ~= nil
  local h, m, s, f = string.match(tc, "(%d+)[:;](%d+)[:;](%d+)[:;](%d+)")
  h, m, s, f = tonumber(h), tonumber(m), tonumber(s), tonumber(f)
  local nom = math.floor(fps + 0.5)
  local total = ((h * 60 + m) * 60 + s) * nom + f
  if df then
    local drop = (nom == 30) and 2 or 4
    local mins = h * 60 + m
    total = total - drop * (mins - math.floor(mins / 10))
  end
  return total
end

local function oa_clip_fps(mpi, default)
  return tonumber(string.match(tostring(mpi:GetClipProperty("FPS") or ""), "[%d%.]+")) or default
end

-- a line per run in script-log.txt, so the app can tell "never ran" from "ran and failed"
local function oa_log(line)
  local f = io.open(OA_DIR .. "script-log.txt", "a")
  if f then f:write(os.date("%Y-%m-%d %H:%M:%S") .. "  " .. line .. "\n"); f:close() end
end

-- run a menu item: whatever `fn` returns goes to the app as inbox-<kind>.json; a problem goes
-- to the app too, so the explanation appears where the operator is looking
local function oa_run(kind, fn)
  print("Original Accent: running (" .. kind .. ")…")
  oa_log("start " .. kind)
  local ok, res = xpcall(fn, function(e) if type(e) == "table" then return e end return { trace = debug.traceback(tostring(e), 2) } end)
  local name = kind == "result" and "outbox-result.json" or ("inbox-" .. kind .. ".json")
  if ok then
    res.ok = true
    if oa_write(name, res) then oa_log("done " .. kind); print("Original Accent: done. Switch back to Original Accent.")
    else oa_log("could not write " .. name) end
  else
    local msg = res.oa or ("Resolve reported a problem: " .. tostring(res.trace))
    oa_log("error " .. kind .. ": " .. msg)
    oa_write(name, { ok = false, error = msg })
    print("Original Accent: " .. msg)
  end
end
