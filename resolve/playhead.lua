-- Menu: Original Accent - Send clip at playhead
-- Sends the clip under the playhead (top video track, else audio) and the part of its source
-- used in the edit, to use as a voice.
oa_run("clip", function()
  local r, project, tl = oa_context(true)
  local fps = oa_fps(project, tl)
  local item = tl:GetCurrentVideoItem()
  if not item or not item:GetMediaPoolItem() then
    item = nil
    local here = oa_tc_to_frames(tl:GetCurrentTimecode(), fps)
    for i = 1, (tl:GetTrackCount("audio") or 0) do
      for _, it in ipairs(oa_objects(tl:GetItemListInTrack("audio", i))) do
        if it:GetStart() <= here and here < it:GetEnd() and it:GetMediaPoolItem() then item = it; break end
      end
      if item then break end
    end
  end
  if not item then oa_fail("There's no clip under the playhead. Move the playhead onto the speaker's clip.") end
  local mpi = item:GetMediaPoolItem()
  local cfps = oa_clip_fps(mpi, fps)
  local a, b
  local ok = pcall(function() a = item:GetSourceStartFrame() / cfps; b = (item:GetSourceEndFrame() + 1) / cfps end)
  if not ok or not a then a = item:GetLeftOffset() / fps; b = a + item:GetDuration() / fps end
  local path = mpi:GetClipProperty("File Path")
  if not path or path == "" then oa_fail("That clip has no file on disk Original Accent can read.") end
  return { path = path, name = mpi:GetName(), range = { a, b }, how = "the part used in the timeline" }
end)
