-- Menu: Original Accent - Send markers
-- Sends the current timeline's markers to Original Accent, which turns them into script parts.
oa_run("markers", function()
  local r, project, tl = oa_context(true)
  local start, list = tl:GetStartFrame(), {}
  for off, m in pairs(tl:GetMarkers() or {}) do
    list[#list + 1] = { frame = start + math.floor(tonumber(off)), color = m.color or "", name = m.name or "", note = m.note or "" }
  end
  table.sort(list, function(a, b) return a.frame < b.frame end)
  return { timeline = tl:GetName(), fps = oa_fps(project, tl), df = oa_df(project, tl), markers = list }
end)
