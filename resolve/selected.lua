-- Menu: Original Accent - Send selected clip
-- Sends the clip selected in the Media Pool (and its In/Out marks, if set) to use as a voice.
oa_run("clip", function()
  local r, project, tl = oa_context(false)
  local sel = project:GetMediaPool():GetSelectedClips() or {}
  local mpi = nil
  for _, c in pairs(sel) do mpi = c; break end
  if not mpi then oa_fail("Select the speaker's clip in the Media Pool first.") end
  local fps = oa_clip_fps(mpi, oa_fps(project, tl))
  local msg = { path = mpi:GetClipProperty("File Path"), name = mpi:GetName(), how = "the whole clip" }
  local ok, mk = pcall(function() return mpi:GetMarkInOut() end)
  if ok and mk then
    local io_ = mk.audio or mk.video
    if io_ and io_["in"] and io_.out and io_.out > io_["in"] then
      msg.range = { io_["in"] / fps, (io_.out + 1) / fps }; msg.how = "its In and Out marks"
    end
  end
  if not msg.path or msg.path == "" then oa_fail("That clip has no file on disk Original Accent can read.") end
  return msg
end)
