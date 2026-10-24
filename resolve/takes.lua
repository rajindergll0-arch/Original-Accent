-- Menu: Original Accent - Bring in takes
-- Imports what Original Accent's "Send to Resolve" prepared, into a bin, and places it on new
-- audio tracks if asked (at the playhead, or at the markers the script came from).
oa_run("result", function()
  local okf, req = pcall(dofile, OA_DIR .. "outbox.lua")
  if not okf or type(req) ~= "table" then oa_fail("Nothing to bring in. In Original Accent, press Send to Resolve on the Deliver page first.") end
  local r, project, tl = oa_context(false)
  local pool = project:GetMediaPool()
  local made = nil
  if #(req.place or {}) > 0 and not tl then
    -- an empty project: make a timeline for the takes rather than refuse
    local name = "Original Accent - " .. (req.job or "takes")
    tl = pool:CreateEmptyTimeline(name)
    if not tl then oa_fail("This project has no timeline, and Resolve wouldn't create one. Create a timeline, then try again.") end
    project:SetCurrentTimeline(tl); made = name
  end
  local folder = pool:GetRootFolder()
  for _, name in ipairs(req.bin) do
    local nxt = nil
    for _, f in pairs(folder:GetSubFolderList() or {}) do if f:GetName() == name then nxt = f; break end end
    folder = nxt or pool:AddSubFolder(folder, name)
    if not folder then oa_fail("Couldn't create the bin " .. name .. " in the Media Pool.") end
  end
  pool:SetCurrentFolder(folder)
  local items = pool:ImportMedia(req.files) or {}
  local byfile, n = {}, 0
  local norm = function(p) return string.lower(string.gsub(p, "/", "\\")) end
  for i, it in pairs(items) do
    n = n + 1
    local p = it:GetClipProperty("File Path") or ""
    byfile[norm(p ~= "" and p or req.files[i])] = it
  end
  if n ~= #req.files then oa_fail("Resolve imported " .. n .. " of " .. #req.files .. " files.") end
  local placed, tracks, ends = {}, {}, {}
  if #(req.place or {}) > 0 then
    local fps = oa_fps(project, tl)
    local here = oa_tc_to_frames(tl:GetCurrentTimecode(), fps)
    table.sort(req.place, function(a, b) return (a.frame or 0) < (b.frame or 0) end)
    for _, p in ipairs(req.place) do
      local start = (p.at == "playhead") and (here + math.floor((p.offset or 0) * fps + 0.5)) or p.frame
      local stop = start + math.max(1, math.floor(p.seconds * fps + 0.5))
      local k = nil
      for i, e in ipairs(ends) do if e <= start then k = i; break end end
      if not k then
        if not tl:AddTrack("audio", "mono") then oa_fail("Resolve wouldn't add an audio track.") end
        local idx = tl:GetTrackCount("audio")
        pcall(function() tl:SetTrackName("audio", idx, (req.track or "Original Accent") .. ((#ends > 0) and (" " .. (#ends + 1)) or "")) end)
        tracks[#tracks + 1] = idx; ends[#ends + 1] = stop; k = #ends
      else
        ends[k] = stop
      end
      local it = byfile[norm(p.file)]
      if not it then oa_fail("Couldn't find " .. p.file .. " in what Resolve imported.") end
      local res = pool:AppendToTimeline({ { mediaPoolItem = it, mediaType = 2, trackIndex = tracks[k], recordFrame = start } })
      if not res then oa_fail("Resolve wouldn't place a take on the timeline.") end
      placed[#placed + 1] = { frame = start, track = tracks[k] }
    end
  end
  os.remove(OA_DIR .. "outbox.lua")       -- done: running the menu again won't import twice
  os.remove(OA_DIR .. "outbox.json")
  return { id = req.id, imported = n, bin = table.concat(req.bin, "/"), placed = placed, tracks = tracks,
           timeline = tl and tl:GetName() or nil, fps = tl and oa_fps(project, tl) or nil, created = made }
end)
