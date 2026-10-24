-- Minimal stand-in for Resolve's Lua scripting API, for tests/test_resolve.py only.
-- Records what the scripts asked for in the global FAKE_LOG, printed as JSON at exit by the test.
FAKE_LOG = { imported = {}, tracks = {}, placed = {} }
local CLIP = os.getenv("OA_TEST_CLIP") or "C:\\media\\interview.wav"
local function obj(t) t.__index = t; return setmetatable({}, t) end
local function item(path, name)
  return obj({ GetName = function() return name or path end,
    GetClipProperty = function(_, k) if k == "File Path" then return path elseif k == "FPS" then return "24" end return "" end,
    GetMarkInOut = function() return { audio = { ["in"] = 24 * 12, out = 24 * 30 - 1 } } end })
end
local root = obj({ GetName = function() return "Master" end, subs = {} })
root.GetSubFolderList = function(self) return self.subs end
local audio = 2
local tl = obj({
  GetName = function() return "Launch film v3" end,
  GetSetting = function(_, k) if k == "timelineFrameRate" then return "24" end return "0" end,
  GetStartFrame = function() return 86400 end,
  GetCurrentTimecode = function() return "01:00:10:00" end,
  GetMarkers = function() return { [48] = { color = "Blue", name = "Intro", note = "This is the new ROG monitor." },
    [216] = { color = "Blue", name = "", note = "It runs at five hundred hertz." }, [360] = { color = "Green", name = "Graphics", note = "" } } end,
  GetCurrentVideoItem = function()
    return obj({ GetMediaPoolItem = function() return item(CLIP, "Interview A-cam") end, GetStart = function() return 86520 end,
      GetEnd = function() return 87000 end, GetSourceStartFrame = function() return 72 end, GetSourceEndFrame = function() return 551 end })
  end,
  GetTrackCount = function(_, k) return k == "audio" and audio or 1 end,
  GetItemListInTrack = function() return {} end,
  AddTrack = function() audio = audio + 1; FAKE_LOG.tracks[#FAKE_LOG.tracks + 1] = audio; return true end,
  SetTrackName = function() return true end,
})
local pool = obj({
  GetRootFolder = function() return root end,
  AddSubFolder = function(_, parent, name)
    local f = obj({ GetName = function() return name end, subs = {} }); f.GetSubFolderList = function(self) return self.subs end
    parent.subs[#parent.subs + 1] = f; return f end,
  SetCurrentFolder = function() return true end,
  GetSelectedClips = function() return { item(CLIP, "Interview A-cam") } end,
  ImportMedia = function(_, files)
    local out = {}
    for i, f in ipairs(files) do FAKE_LOG.imported[#FAKE_LOG.imported + 1] = f; out[i] = item(f) end
    return out end,
  AppendToTimeline = function(_, infos)
    for _, i in ipairs(infos) do FAKE_LOG.placed[#FAKE_LOG.placed + 1] = { file = i.mediaPoolItem:GetClipProperty("File Path"), track = i.trackIndex, frame = i.recordFrame, mediaType = i.mediaType } end
    return infos end,
})
local current = tl
if os.getenv("OA_TEST_NO_TIMELINE") then current = nil end
pool.CreateEmptyTimeline = function(_, name) FAKE_LOG.created = name; return tl end
local project = obj({ GetCurrentTimeline = function() return current end, GetMediaPool = function() return pool end,
  SetCurrentTimeline = function(_, t) current = t; return true end,
  GetSetting = function(_, k) return tl:GetSetting(k) end })
resolve = obj({ GetProjectManager = function() return obj({ GetCurrentProject = function() return project end }) end })
