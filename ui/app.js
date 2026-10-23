/* Original Accent front end. No build step: plain JS against the local API.
   Rendering is "state -> HTML string -> innerHTML", then canvases are drawn. Every page
   is shared across skins except Compare, which has a layout per skin. */
"use strict";
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const S = { boot: null, page: "voice", voiceId: null, job: null, jobId: null, part: 0, sel: 0, run: null, playing: null,
  draft: null, setupDismissed: false, exportResult: null, trim: null };
const PAGES = [["voice", "Voice"], ["script", "Script"], ["generate", "Generate"], ["compare", "Compare"], ["deliver", "Deliver"], ["settings", "Settings"]];
const SKINS = { grade: ["Grade", "Editor panels, pages along the bottom", ["#1c1c1e", "#ff4d3d", "#7ec4ff", "#3a3a3c"]],
  reel: ["Reel", "Edit-suite tracks and timecode", ["#0E1424", "#4CC9E8", "#F2A541", "#172138"]],
  signal: ["Signal", "An audio instrument: scope and channel strips", ["#0A0B0A", "#C6FF3D", "#8C9488", "#141813"]],
  booth: ["Booth", "One take at a time, almost no chrome", ["#16120F", "#FF3B2F", "#EFE7DF", "#4A3F36"]] };
/* per-skin trim of the base size, so the four typefaces read at the same apparent size:
   Signal's monospace UI face is wider and taller per point than the others */
const SKIN_SCALE = { grade: 1, reel: 1, signal: 0.94, booth: 1 };
const ENG = { qwen: ["Qwen3-TTS", "q", "var(--qwen)"], cbx: ["Chatterbox", "c", "var(--cbx)"] };

async function api(name, args = {}) {
  const r = await fetch(`/api/${name}`, { method: "POST", headers: { "Content-Type": "application/json", "X-Token": VC_TOKEN }, body: JSON.stringify(args) });
  const j = await r.json();
  if (!j.ok) throw new Error(j.error || "Request failed");
  return j.data;
}
const media = (key) => { const [k, a, b] = key.split(":"); return k === "v" ? `/media/voice/${a}?t=${VC_TOKEN}` : k === "f" ? `/media/full/${a}?t=${VC_TOKEN}` : `/media/take/${a}/${b}?t=${VC_TOKEN}`; };
/* Notices. Info toasts close themselves (or with ×). Errors open a panel that stays until
   closed, can be dragged out of the way, and keeps the technical text behind "Show details". */
function toast(msg) {
  const d = document.createElement("div"); d.className = "toast"; d.setAttribute("role", "status");
  d.innerHTML = `<span>${esc(tsText(msg))}</span><button class="x" aria-label="Close">×</button>`;
  $("#toasts").appendChild(d);
  const t = setTimeout(() => d.remove(), 4500);
  d.querySelector(".x").onclick = () => { clearTimeout(t); d.remove(); };
}
function showError(summary, detail, log) {
  $("#errpanel")?.remove();
  const d = document.createElement("div"); d.id = "errpanel"; d.className = "notice"; d.setAttribute("role", "alertdialog"); d.setAttribute("aria-label", "Error");
  d.innerHTML = `<div class="nh" title="Drag to move"><span class="dot" style="background:#ff7a6e"></span><strong>Something went wrong</strong><span class="spacer"></span><button class="x" aria-label="Close">×</button></div>
    <div class="nb"><p style="margin:0">${esc(summary)}</p>${detail ? `<details><summary>Show details</summary><pre class="err">${esc(detail)}</pre></details>` : ""}
    <div class="row">${detail ? '<button class="btn sm" data-n="copy">Copy details</button>' : ""}${log ? '<button class="btn sm" data-n="logs">Open log folder</button>' : ""}<span class="spacer"></span><button class="btn sm" data-n="close">Close</button></div></div>`;
  document.body.appendChild(d);
  d.querySelector(".x").onclick = () => d.remove();
  d.addEventListener("click", (e) => {
    const n = e.target.dataset?.n;
    if (n === "close") d.remove();
    else if (n === "copy") navigator.clipboard?.writeText(`${summary}\n\n${detail}`).then(() => toast("Details copied"));
    else if (n === "logs") api("open_folder", { path: log.replace(/[\\/][^\\/]*$/, "") }).catch(() => {});
  });
  draggable(d, d.querySelector(".nh"));
}
function draggable(el, handle) {
  handle.addEventListener("pointerdown", (e) => {
    if (e.target.closest("button")) return;
    const r = el.getBoundingClientRect(), ox = e.clientX - r.left, oy = e.clientY - r.top;
    handle.setPointerCapture(e.pointerId);
    const mv = (ev) => { Object.assign(el.style, { left: Math.max(0, Math.min(innerWidth - r.width, ev.clientX - ox)) + "px", top: Math.max(0, Math.min(innerHeight - 48, ev.clientY - oy)) + "px", right: "auto", bottom: "auto" }); };
    const up = () => { handle.removeEventListener("pointermove", mv); handle.removeEventListener("pointerup", up); };
    handle.addEventListener("pointermove", mv); handle.addEventListener("pointerup", up);
  });
}
function modal(html) {
  const o = document.createElement("div"); o.className = "overlay modal";
  o.innerHTML = `<div class="panel setup" role="dialog" aria-modal="true">${html}</div>`;
  document.body.appendChild(o);
  o.addEventListener("click", (e) => {
    const m = e.target.dataset?.m;
    if (m === "close" || e.target === o) o.remove();
    else if (m === "restart") { o.querySelector(".setup").innerHTML = '<p class="lead">Restarting Original Accent…</p>'; api("restart").catch(() => {}); }
  });
}
function showDone(names, updated) {
  const t = (names || []).map((n) => S.boot.engines[n]?.title || n), many = t.length > 1;
  modal(`<div class="kicker">${updated ? "Update complete" : "Setup complete"}</div><h2 class="h1" style="font-size:1.7rem">${many ? "Engines" : "Engine"} ${updated ? "updated" : "ready"}</h2>
    <p class="lead">${esc(t.join(", ")) || "The engines"} ${many ? "are" : "is"} ${updated ? "up to date" : "installed"} and can be used straight away. A restart isn't needed, but you can restart now if you'd like a clean start.</p>
    <div class="row"><button class="btn" data-m="restart">Restart Original Accent</button><span class="spacer"></span><button class="btn primary" data-m="close">Done</button></div>`);
}
async function guard(fn) { try { return await fn(); } catch (e) { showError(e.message); } }

/* ---------------- boot + polling ---------------- */
async function boot() {
  S.boot = await api("bootstrap");
  applySettings();
  S.run = S.boot.run;
  if (S.boot.voices.length) S.voiceId = S.boot.voices[0].id;
  if (S.boot.jobs.length) await openJob(S.boot.jobs[0].id, false);
  render();
  setInterval(poll, 900);
  // engine update check: at most once a day, metadata only (PyPI, Hugging Face)
  S.updates = await api("updates_last").catch(() => null);
  const age = S.updates?.checked && Object.values(S.updates.engines || {}).every((e) => e.installed) ? (Date.now() - Date.parse(S.updates.checked)) / 36e5 : 1e9;   // results saved before versions were listed count as stale
  if (S.boot.settings.check_updates && age > 24 && !needsSetup()) api("updates_check").then((u) => { S.updates = u; if (u.any) { toast("Engine updates are available. See Settings."); renderNav(); } }).catch(() => {});
  // engines chosen in the Windows installer: start installing them straight away
  const ch = S.boot.choices;
  if (ch) {
    await api("choices_clear");
    const missing = (ch.engines || []).filter((n) => !S.boot.engines[n]?.installed);
    S.setupSel = Object.fromEntries(["qwen", "score", "cbx"].map((n) => [n, (ch.engines || []).includes(n) || n === "qwen"]));
    if (missing.length && S.boot.gpu.ok && S.run?.state !== "running") {
      await api("setup_install", { engines: missing }); S.run = await api("run_state"); render();
      if (!needsSetup()) toast(`Installing ${missing.map((n) => S.boot.engines[n].title).join(", ")}…`);
    }
  }
}
function applySettings() {
  const s = S.boot.settings;
  document.body.dataset.sk = s.skin;
  document.documentElement.style.setProperty("--ui-scale", s.ui_scale);
  document.documentElement.style.setProperty("--skin-scale", SKIN_SCALE[s.skin] || 1);
}
let lastState = null;
async function poll() {
  const r = await api("run_state").catch(() => null);
  if (!r) return;
  const changed = JSON.stringify(r) !== JSON.stringify(S.run);
  S.run = r;
  if (r.state === "running" && r.kind === "job" && r.job === S.jobId && changed) S.job = await api("job_get", { id: S.jobId });
  if (lastState === "running" && r.state !== "running") {
    S.boot.engines = await api("engines"); S.boot.voices = await api("voices");
    if (S.jobId) S.job = await api("job_get", { id: S.jobId });
    if (r.state === "error") showError(r.error || "Failed", r.error_detail, r.error_log);
    else if (r.kind === "setup" && r.state === "done") { showDone(r.finished, /updated/.test(r.message || "")); S.updates = await api("updates_last").catch(() => null); }
    else if (r.message) toast(r.message);
    if (r.kind === "job" && r.state === "done" && S.page === "generate") S.page = "compare";
    render();
  } else if (changed) {
    // re-render only pages that show this run's progress, so typing elsewhere is never clobbered
    const shows = S.page === "generate" || (S.page === "voice" && r.kind === "transcribe") ||
      (S.page === "settings" && r.kind === "setup") || $("#overlay").innerHTML;
    if (shows) render(); else renderTop();
  }
  lastState = r.state;
}
async function openJob(id, go = true) { S.jobId = id; S.job = await api("job_get", { id }); S.part = 0; S.sel = 0; if (go) { S.page = "compare"; render(); } }

/* ---------------- render ---------------- */
function render() { renderTop(); renderNav(); renderPage(); renderOverlay(); typeset(document.body); requestAnimationFrame(() => { fitPreviews(); drawAll(); }); }
/* Typesetting pass over rendered prose: keep units with their numbers ("40 seconds", "6–15 s"),
   and keep short quotes and parentheticals ("(for example “G X ten”)") on one line, by swapping
   their spaces for non-breaking ones. Inputs and text areas are never touched. */
const NB = "\u00A0", WJ = "\u2060";   // no-break space; word joiner (invisible, forbids a break)
function tsText(t) { return tsPass(tsPass(t)); }   // twice: neighbouring short words ("so up to") overlap
function tsPass(t) {
  return t
    .replace(/(\d[\d.,–½]*)\s+(s|ms|seconds?|minutes?|mins?|words?|GB|MB|dB|dBFS|%|takes?|parts?|chunks?)\b/g, `$1${NB}$2`)
    .replace(/\(([^()]{1,40})\)/g, (m) => m.replace(/ /g, NB))
    .replace(/“([^”]{1,28})”/g, (m) => m.replace(/ /g, NB))
    .replace(/ ([–—]) /g, `${NB}$1 `)
    // hyphenated compounds and number ranges never split across lines ("multi-agent", "6–15")
    .replace(/(\p{L}|\d)([-–])(?=\p{L}|\d)/gu, `$1${WJ}$2${WJ}`)
    // short words (three letters or fewer) never sit alone at the end of a line: they travel
    // with the word after them, which also covers a short word straight after ; : , or .
    .replace(/(^|[\s(“])([\p{L}\d']{1,3}) (?=[\p{L}\d(“])/gu, (m, a, w) => `${a}${w}${NB}`);
}
/* Text areas grow with what's typed or pasted (up to a cap, then scroll), so the box always
   fits its text instead of hiding most of a script behind a scrollbar. */
function autosize(el) {
  const cs = getComputedStyle(el), min = parseFloat(cs.minHeight) || 0, max = Math.max(min, innerHeight * 0.6);
  el.style.height = "auto"; el.style.height = Math.min(max, Math.max(min, el.scrollHeight + 2)) + "px";
  el.style.overflowY = el.scrollHeight + 2 > max ? "auto" : "hidden";
}
function typeset(root) {
  root.querySelectorAll("textarea.input").forEach(autosize);
  root.querySelectorAll(".lead, .note, .gbody p, .gbody li, .toast span, .notice p, .h1, label > span, .switch span").forEach((el) => {
    if (el.closest(".pv") || el.dataset.ts === "1") return;
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) { const v = tsText(n.nodeValue); if (v !== n.nodeValue) n.nodeValue = v; }
    el.dataset.ts = "1";
  });
}
function renderTop() { $("#top").innerHTML = topHTML(); }
function topHTML() {
  const r = S.run || {}, g = S.boot.gpu || {}, busy = r.state === "running";
  const jobName = S.job ? S.job.name : "No job open";
  return `<span class="tally ${busy ? "on" : ""}" title="${busy ? "Working" : "Idle"}"></span>
    <span class="brand">Original Accent</span><span class="mute small trunc" style="max-width:32vw" title="${esc(jobName)}">${esc(jobName)}</span>
    ${S.boot.demo ? `<span class="tag" style="color:var(--cbx)">Demo mode · simulated engines</span>` : ""}
    <span class="spacer"></span>
    ${busy ? `<span class="small">${esc(r.stage)}${r.total ? ` · ${r.done}/${r.total}` : ""}</span>` : ""}
    <span class="mono small mute">${g.ok ? `${esc(g.name)} · ${g.used_gb}/${g.total_gb} GB` : "No NVIDIA GPU found"}</span>`;
}
function renderNav() { $("#nav").innerHTML = navHTML(); }
function navHTML() {
  return PAGES.map(([id, label], i) => {
    const off = (id === "compare" || id === "deliver" || id === "generate") && !S.job;
    return `<button class="navbtn" data-go="${id}" ${S.page === id ? 'aria-current="page"' : ""} ${off ? "disabled" : ""}>
      <span class="tc">00:0${i + 1}:00:00</span><span>${label}</span>${id === "settings" && S.updates?.any ? '<span class="dot" style="background:var(--accent)" title="Updates available"></span>' : ""}</button>`;
  }).join("");
}
let shownPage = null;
function renderPage() {
  const m = $("#main");
  // a new page starts at the top; re-drawing the same page (progress, playback) keeps your place
  if (shownPage !== S.page) { m.scrollTop = 0; shownPage = S.page; }
  m.innerHTML = { voice: pageVoice, script: pageScript, generate: pageGenerate, compare: pageCompare, deliver: pageDeliver, settings: pageSettings }[S.page]();
  m.firstElementChild?.classList.add("fade");
}

/* ---------------- setup overlay ---------------- */
const ENGINE_INFO = {
  qwen: ["Required", "The voice engine. Clones a voice from a short clip and its transcript, and keeps the speaker's accent."],
  score: ["Recommended", "Whisper writes the first draft of the clip's transcript and checks each take says the right words; the speaker check scores how close each take sounds to the reference. Without it you type transcripts yourself and judge takes by ear alone."],
  cbx: ["Optional", "A second voice engine that makes takes a different way: more variety, or a fallback when a line keeps coming out wrong. It can soften an accent, so you can choose whether it is used for each run. Its audio carries Resemble AI's inaudible Perth watermark."] };
/* per-engine install status, shown inline on that engine's row: step x of y, a bar, what the
   installer last reported, and how long this step has been running */
function since(t) { if (!t) return ""; const s = Math.max(0, Math.round(Date.now() / 1000 - t)); return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`; }
function engStatus(n) {
  const r = S.run || {}, e = S.boot.engines[n], setup = r.kind === "setup";
  if (setup && r.state === "running" && r.engine === n) {
    const pct = Math.round((100 * ((r.step_i || 0) + 0.5)) / (r.step_n || 6));
    return `<div class="eprog"><div class="row small" style="flex-wrap:nowrap;gap:.5rem"><span class="trunc"><b>Step ${(r.step_i || 0) + 1} of ${r.step_n || 6}</b> · ${esc(r.step_text || "Starting")}</span><span class="spacer"></span><span class="mono mute" data-since="${r.step_started || ""}" title="Time on this step">${since(r.step_started)}</span></div>
      <div class="bar"><i style="width:${pct}%"></i></div><div class="small mute trunc" title="${esc(r.detail || "")}">${esc(r.detail || "Working…")}</div></div>`;
  }
  if (setup && r.state === "running" && (r.queue || []).includes(n) && !(r.finished || []).includes(n)) return `<span class="small mute">Queued, starts after the current engine</span>`;
  if (setup && r.state === "error" && r.engine === n) return `<span class="small" style="color:#ff7a6e">Install failed. See the error panel, or press ${e.installed ? "Repair" : "Install"} to try again.</span>`;
  return `<span class="small mute">${e.installed ? "Installed" : e.required ? "Required · not installed" : "Optional · not installed"}</span>`;
}
setInterval(() => document.querySelectorAll("[data-since]").forEach((el) => { if (el.dataset.since) el.textContent = since(+el.dataset.since); }), 1000);
function needsSetup() { return !S.boot.engines.qwen.installed; }
function setupSel() { if (!S.setupSel) S.setupSel = { qwen: true, score: true, cbx: true }; return S.setupSel; }
function renderOverlay() {
  const o = $("#overlay");
  if (!needsSetup() || S.setupDismissed) { o.innerHTML = ""; return; }
  const e = S.boot.engines, g = S.boot.gpu, r = S.run || {}, busy = r.state === "running" && r.kind === "setup", sel = setupSel();
  o.innerHTML = `<div class="overlay"><div class="setup panel">
    <div class="kicker">First run</div><h1 class="h1">Set up the voice engines</h1>
    <p class="lead">Everything runs on this PC. Nothing is sent to a cloud service. Setup downloads the open-source engines and their models once (several GB each); after that Original Accent works offline.</p>
    <div class="panel" style="background:var(--deep)"><div class="row"><span class="dot" style="background:${g.ok ? "var(--voice)" : "#ff7a6e"}"></span>
      <strong>${g.ok ? esc(g.name) : "No NVIDIA GPU detected"}</strong><span class="mute small">${g.ok ? `${g.total_gb} GB video memory` : esc(g.error || "")}</span></div></div>
    ${["qwen", "score", "cbx"].map((n) => `<label class="switch panel"><input type="checkbox" data-eng="${n}" ${sel[n] || n === "qwen" ? "checked" : ""} ${n === "qwen" || busy ? "disabled" : ""}>
      <span><strong>${esc(e[n].title)}</strong> ${e[n].installed ? '<span class="tag" style="color:var(--voice)">Installed</span>' : `<span class="tag ${n === "qwen" ? "mute" : n === "score" ? "" : "c"}" ${n === "score" ? 'style="color:var(--words)"' : ""}>${ENGINE_INFO[n][0]}</span>`}<br>
      <span class="note">${ENGINE_INFO[n][1]}</span>${busy && (r.queue || []).includes(n) ? `<span class="estat" style="display:block;margin-top:.6rem">${engStatus(n)}</span>` : ""}</span></label>`).join("")}
    ${busy ? `<div class="field"><span class="small">${esc(r.stage)}</span><div class="bar"><i style="width:${r.total ? Math.max(4, (100 * r.done) / r.total) : 4}%"></i></div></div>` : ""}
    <div class="row"><button class="btn primary" data-act="install" ${busy || !g.ok ? "disabled" : ""}>${busy ? "Installing…" : "Install engines"}</button>
      <span class="note">You can keep using the PC meanwhile.</span><span class="spacer"></span>
      <button class="btn" data-act="skip-setup">Later</button></div>
  </div></div>`;
}

/* ---------------- Voice ---------------- */
function curVoice() { return S.boot.voices.find((v) => v.id === S.voiceId); }
function trimOf(v) {
  if (!S.trim || S.trim.id !== v.id) S.trim = { id: v.id, s: v.trim ? v.trim[0] : 0, e: v.trim ? v.trim[1] : (v.full_duration || v.duration), reason: null };
  return S.trim;
}
function trimNote(T) {
  const d = T.e - T.s;
  return `${d.toFixed(1)} s selected · ${d < 6 ? "under 6 s: cloning may be weaker" : d > 15 ? "over 15 s: shorten to the cleanest 6–15 s" : "good length"}`;
}
function pageVoice() {
  const v = curVoice(), r = S.run || {}, tr = r.state === "running" && r.kind === "transcribe", wsp = S.boot.engines.score.installed;
  const T = v ? trimOf(v) : null, changed = v && (!v.trim || Math.abs(v.trim[0] - T.s) > 0.01 || Math.abs(v.trim[1] - T.e) > 0.01) && !(!v.trim && T.s === 0 && Math.abs(T.e - (v.full_duration || v.duration)) < 0.01);
  return `<div class="page"><div><div class="kicker">Step 1 · operator</div><h1 class="h1">Voice</h1>
    <p class="lead">Add a recording of the speaker: one voice, no music. Audio or video files up to 3 hours are fine. Original Accent picks the cleanest 6–15 seconds to clone from; listen, and move the section if you prefer another part.</p></div>
    <div class="cols"><div class="panel" style="padding:0">
      <div style="margin:.9rem .9rem 0"><label class="switch"><input type="checkbox" id="consent" ${S.consent ? "checked" : ""}><span>I have the speaker's permission to clone their voice<br><span class="note">Required before adding a recording. Cloning someone's voice without consent can be unlawful and harmful.</span></span></label></div>
      <div class="drop ${S.consent ? "" : "locked"}" id="drop" style="margin:.9rem">${S.consent ? "Drop an audio or video file here" : "Tick the permission box to add a recording"}<br><span class="small">Up to 3 hours of audio, or 4 GB</span><br>
        <label class="btn" style="margin-top:.5rem" ${S.consent ? "" : 'aria-disabled="true"'}>Choose file<input type="file" id="file" accept="audio/*,video/*" hidden ${S.consent ? "" : "disabled"}></label></div>
      <div class="list">${S.boot.voices.map((x) => `<button class="item" data-voice="${x.id}" aria-selected="${x.id === S.voiceId}">
        <span class="dot" style="background:var(--ref)"></span><span class="grow"><strong class="trunc" title="${esc(x.name)}">${esc(x.name)}</strong><span class="small mute trunc">${x.duration}s · ${x.transcript ? "transcript ready" : "needs transcript"}</span></span></button>`).join("") || `<p class="note" style="padding:0 1rem">No voices yet.</p>`}</div>
    </div>
    ${v ? `<div style="display:flex;flex-direction:column;gap:1.1rem">
      <div class="panel"><div class="field"><label for="vname">Name</label><input class="input" id="vname" value="${esc(v.name)}"></div></div>
      <div class="panel" style="display:flex;flex-direction:column;gap:.8rem">
        <div class="row"><strong>Section to clone from</strong><span class="spacer"></span><span class="mono small mute">whole file · ${fmt(v.full_duration || v.duration)}</span></div>
        <canvas class="wave" data-wave="f:${v.id}" data-trim="1" data-color="var(--ref)" style="height:6.5rem" aria-label="Recording waveform. Click or drag to move the playhead; drag the handles to set the section; scroll to step through."></canvas>
        <div class="row">${transport("f:" + v.id)}<button class="btn" data-act="play-sel">▶ Play selection</button><span class="spacer"></span>
          <button class="btn" data-act="suggest" title="Finds continuous, clean speech that starts and ends in a pause">✦ Suggest cleanest section</button></div>
        <div class="row"><div class="field"><label for="ts">Start (s)</label><input class="input mono" id="ts" type="number" step="0.1" min="0" value="${T.s}" style="width:7.5rem"></div>
          <div class="field"><label for="te">End (s)</label><input class="input mono" id="te" type="number" step="0.1" min="0" value="${T.e}" style="width:7.5rem"></div>
          <button class="btn ${changed ? "primary" : ""}" data-act="trim" style="align-self:flex-end">Apply section</button>
          <span class="note" id="tsel" style="align-self:flex-end">${trimNote(T)}</span></div>
        <p class="note" style="margin:0">${T.reason ? `Suggested: ${esc(T.reason)}. Listen, adjust the handles if needed, then apply.` : v.auto_trimmed ? "This recording was long, so Original Accent picked the cleanest section for you. Listen, adjust if needed." : "Drag the handles on the waveform, type times, or let Original Accent suggest the cleanest section. Click the waveform to jump; scroll over it to step through."}</p>
      </div>
      <div class="panel" style="display:flex;flex-direction:column;gap:.7rem">
        <div class="row"><strong>Reference used for cloning</strong><span class="spacer"></span><span class="mono small mute">${v.duration} s</span></div>
        <canvas class="wave" data-wave="v:${v.id}" data-color="var(--qwen)" style="height:3.4rem"></canvas>
        <div class="row">${transport("v:" + v.id)}</div>
      </div>
      <div class="panel" style="display:flex;flex-direction:column;gap:.8rem">
        <div class="field"><label for="vtx">Transcript of the reference, word for word</label>
          <textarea class="input" id="vtx" placeholder="Type exactly what is said in the reference${wsp ? ", or let Whisper draft it" : ""}.">${esc(v.transcript)}</textarea></div>
        <div class="row"><button class="btn" data-act="transcribe" ${!wsp || tr || r.state === "running" ? "disabled" : ""}>${tr ? "Drafting…" : "Draft with Whisper"}</button>
          <button class="btn primary" data-act="save-voice">Save</button><span class="spacer"></span>
          <button class="btn" data-go="script" ${v.transcript ? "" : "disabled"}>Next: script →</button></div>
        <p class="note" style="margin:0">${wsp ? "Check the draft against the reference. Full-reference cloning relies on the transcript matching the audio exactly. Re-draft after changing the section." : "Whisper isn't installed, so type the transcript. You can add Whisper in Settings to have it drafted for you."}</p>
      </div></div>` : `<div class="panel note">Add a voice to begin.</div>`}</div></div>`;
}
function updateTrimFields() { const T = S.trim; if (!T) return; const a = $("#ts"), b = $("#te"); if (a) a.value = T.s; if (b) b.value = T.e; const n = $("#tsel"); if (n) n.textContent = trimNote(T); }

/* ---------------- Script ---------------- */
function draft() {
  if (!S.draft) { const s = S.boot.settings; S.draft = { name: "", voice_id: S.voiceId, parts: [{ label: "Part 1", text: "" }], takes_per_part: s.takes_per_part, include_chatterbox: s.include_chatterbox && S.boot.engines.cbx.installed }; }
  if (!S.draft.voice_id) S.draft.voice_id = S.voiceId;
  return S.draft;
}
function pageScript() {
  const d = draft(), cbxOk = S.boot.engines.cbx.installed;
  const n = d.parts.length * (d.takes_per_part + (d.include_chatterbox ? S.boot.settings.chatterbox_configs.length : 0));
  return `<div class="page"><div><div class="kicker">Step 2 · operator</div><h1 class="h1">Script</h1>
    <p class="lead">Paste the lines exactly as they should be spoken. Spell out anything that must be pronounced a certain way (for example “G X ten”).</p>
    <p class="note" style="margin:.4rem 0 0">Each part is spoken in one go. Up to about 90 words (around 40 seconds) suits both engines; Qwen on its own manages about 350 words (around 2½ minutes). Longer parts can be auto-split: see About long scripts below.</p></div>
    ${longGuide(d.parts.some((p) => p.group || words(p.text) > chunkTarget(d.include_chatterbox)))}
    <div class="cols"><div class="panel" style="display:flex;flex-direction:column;gap:1rem">
      <div class="field"><label for="jname">Job name</label><input class="input" id="jname" value="${esc(d.name)}" placeholder="e.g. Launch video narration"></div>
      <div class="field"><label for="jvoice">Voice</label><select class="input" id="jvoice">${S.boot.voices.map((v) => `<option value="${v.id}" ${v.id === d.voice_id ? "selected" : ""}>${esc(v.name)}${v.transcript ? "" : " (needs transcript)"}</option>`).join("")}</select></div>
      <div class="field"><label for="jtakes">Qwen takes per part</label><div class="row"><input class="input mono" id="jtakes" type="number" min="1" max="8" value="${d.takes_per_part}" style="width:6rem"><span class="note">More takes, more to choose from; each adds time.</span></div></div>
      <div class="panel" style="background:var(--deep)"><label class="switch"><input type="checkbox" id="jcbx" ${d.include_chatterbox ? "checked" : ""} ${cbxOk ? "" : "disabled"}>
        <span><strong>Include Chatterbox takes</strong><br><span class="note">Adds takes from a second model, made a different way, so you have more to choose from.<br>
        <b>Leave on when</b> a line keeps coming out wrong from Qwen, or you want more variety in delivery.<br>
        <b>Turn off when</b> keeping the speaker's accent matters most, or you want faster runs. Qwen is better at keeping an accent; Chatterbox can soften it.<br>
        Chatterbox marks everything it makes with an inaudible watermark (Resemble AI's Perth), so its takes can be identified as AI-generated.
        ${cbxOk ? "" : "<br><b>Not installed.</b> Add it in Settings."}</span></span></label></div>
      <div class="note">This run makes <b>${n}</b> take${n === 1 ? "" : "s"}. Each take is labelled with the model that made it.</div>
      <button class="btn primary" data-act="generate">Generate takes</button>
      ${S.boot.jobs.length ? `<div class="field"><label>Open an earlier job</label><div class="list">${S.boot.jobs.slice(0, 6).map((j) => `<button class="item" data-job="${j.id}"><span class="grow"><span class="trunc" title="${esc(j.name)}">${esc(j.name)}</span><span class="small mute trunc">${esc(j.created.replace("T", " "))} · ${j.parts} part(s)</span></span></button>`).join("")}</div></div>` : ""}
    </div>
    <div style="display:flex;flex-direction:column;gap:1rem">${d.parts.map((p, i) => `<div class="panel" style="display:flex;flex-direction:column;gap:.6rem">
      <div class="row"><input class="input" data-plabel="${i}" value="${esc(p.label)}" style="max-width:16rem;min-width:8rem;flex:1"><span class="spacer"></span>
      ${p.group ? `<span class="tag" style="color:var(--words)" title="Chunk of “${esc(p.group)}”; ends ${p.brk === "para" ? "a paragraph" : "mid-paragraph"}">${p.brk === "para" ? "¶ end" : "mid ¶"}</span>` : ""}
      <span class="mono small mute" data-wc="${i}">${wcText(p.text)}</span>
      ${words(p.text) > chunkTarget(d.include_chatterbox) ? `<button class="btn sm" data-split="${i}" title="Split at paragraph and sentence ends into chunks of about ${chunkTarget(d.include_chatterbox)} words">Auto-split</button>` : ""}
      ${p.group && d.parts.findIndex((x) => x.group === p.group) === i ? `<button class="btn sm" data-merge="${esc(p.group)}">Merge chunks</button>` : ""}
      ${d.parts.length > 1 ? `<button class="btn sm" data-delpart="${i}">Remove</button>` : ""}</div>
      <textarea class="input" data-ptext="${i}" style="min-height:9rem" placeholder="Script text for this part">${esc(p.text)}</textarea>
      <span class="note" data-lim="${i}">${limitNote(p.text, d.include_chatterbox)}</span></div>`).join("")}
      <div class="row"><button class="btn" data-act="addpart">+ Add part</button>${d.parts.some((p) => words(p.text) > chunkTarget(d.include_chatterbox)) ? `<button class="btn" data-act="split-all">Auto-split all long parts</button>` : ""}</div></div></div></div>`;
}

/* Length guide per part. Limits come from each engine's maximum output per generation:
   Qwen3-TTS caps at 2048 codec tokens (12 Hz codec, ~170 s); Chatterbox at ~1000 speech tokens
   (25 Hz, ~40 s). At a narration pace of ~140 words a minute that is ~350 and ~90 words. */
const WPS = 140 / 60;
function words(t) { return t.trim() ? t.trim().split(/\s+/).length : 0; }
function dur(sec) { sec = Math.round(sec); return sec < 90 ? `${sec} s` : `${Math.floor(sec / 60)} min ${String(sec % 60).padStart(2, "0")} s`; }
function wcText(t) { const n = words(t); return n ? `${n} word${n === 1 ? "" : "s"} · about ${dur(n / WPS)}` : "No text yet"; }
function limitNote(t, cbx) {
  const n = words(t);
  if (n > 350) return `<span style="color:#ff7a6e">Too long for one part: Qwen may stop before the end. Use Auto-split.</span>`;
  if (n > 90 && cbx) return `<span style="color:var(--cbx)">Over about 90 words, Chatterbox takes may cut off before the end. Qwen takes will be complete. Use Auto-split if you want full Chatterbox takes.</span>`;
  return "";
}

/* ---------------- long scripts: split, guidance ----------------
   Each part is spoken in one generation. Longer pieces are split into chunks (paragraph ends
   first, then sentence ends), generated separately, and joined on export. */
function chunkTarget(cbx) { return cbx ? 80 : 150; }   // comfortable words per chunk
function splitText(text, max) {
  const out = [], paras = text.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  for (const para of paras) {
    const chunks = [];
    if (words(para) <= max) chunks.push(para);
    else {
      const sents = para.match(/[^.!?…]+(?:[.!?…]+["”’)\]]*|$)/g)?.map((x) => x.trim()).filter(Boolean) || [para];
      let cur = "";
      for (const sn of sents) {
        const pieces = words(sn) > max ? sn.split(/(?<=[,;:—–])\s+/) : [sn];   // over-long sentence: break at clause marks
        for (const pc of pieces) {
          if (cur && words(cur) + words(pc) > max) { chunks.push(cur); cur = ""; }
          if (words(pc) > max) { const w = pc.split(/\s+/); for (let k = 0; k < w.length; k += max) chunks.push(w.slice(k, k + max).join(" ")); }
          else cur = cur ? `${cur} ${pc}` : pc;
        }
      }
      if (cur) chunks.push(cur);
    }
    chunks.forEach((c, k) => out.push({ text: c, brk: k === chunks.length - 1 ? "para" : "sentence" }));
  }
  return out;
}
function splitPart(i) {
  const d = draft(), p = d.parts[i], group = p.group || p.label || `Part ${i + 1}`;
  const ch = splitText(p.text, chunkTarget(d.include_chatterbox));
  if (ch.length < 2) return 0;
  d.parts.splice(i, 1, ...ch.map((c, k) => ({ label: `${group} · ${k + 1}/${ch.length}`, text: c.text, group, brk: c.brk })));
  return ch.length;
}
function mergeGroup(group) {
  const d = draft(), idx = d.parts.map((p, i) => (p.group === group ? i : -1)).filter((i) => i >= 0);
  if (!idx.length) return;
  const text = idx.map((i) => d.parts[i]).reduce((acc, p, k, arr) => acc + p.text + (k < arr.length - 1 ? (p.brk === "para" ? "\n\n" : " ") : ""), "");
  d.parts.splice(idx[0], idx.length, { label: group, text });
}
function longGuide(open) {
  return `<details class="guide panel" ${open ? "open" : ""}><summary><strong>About long scripts</strong> <span class="small mute">how splitting and joining affect the sound</span></summary>
    <div class="gbody">
      <p>Qwen can speak about <b>2½ minutes</b> per part and Chatterbox about <b>40 seconds</b>. A longer script needs splitting into chunks, which are generated separately and joined when you export. <b>Auto-split</b> does this for you; the chunks appear as parts labelled 1/4, 2/4 and so on.</p>
      <p><b>What stays the same:</b> every chunk is cloned from the same reference, so the voice, timbre and accent carry through.</p>
      <p><b>What can vary between chunks:</b> pace, energy, pitch and loudness, and how a chunk starts or ends. You hear it at the joins, mostly where a split lands mid-paragraph. Inside a chunk, delivery is continuous.</p>
      <p><b>To keep it seamless:</b></p>
      <ul>
        <li>Split at paragraph or section ends where you can. Auto-split does that first, and only splits sentences when a paragraph is too long.</li>
        <li>Picking the same take number in each chunk may help, because those takes share a random seed. It's a nudge, not a guarantee: trust your ear.</li>
        <li>On Deliver, use <b>Play all picks</b> to listen through the joins, and re-pick any chunk that stands out.</li>
        <li>The joined export trims each chunk's edges, matches loudness, and adds a short pause inside a paragraph, a longer one at a paragraph end, and a longer one again between separate parts.</li>
      </ul>
      <p class="mute small">Original Accent clones every chunk from your original reference, never from the chunk before. Chaining one output into the next makes the voice drift.</p>
    </div></details>`;
}

/* ---------------- Generate ---------------- */
function pageGenerate() {
  const j = S.job, r = S.run || {}, mine = r.kind === "job" && r.job === S.jobId;
  const stages = [["Freeing GPU memory", "Free GPU"], ["Cloning · Qwen3-TTS", "Clone · Qwen3-TTS"]];
  if (j.include_chatterbox) stages.push(["Cloning · Chatterbox", "Clone · Chatterbox"]);
  stages.push(["Checking · Whisper + speaker check", "Check · words and voice"]);
  const at = mine ? stages.findIndex((s) => s[0] === r.stage) : -1, done = mine && r.state === "done";
  const ready = j.takes.filter((t) => t.ready).length;
  return `<div class="page"><div><div class="kicker">Step 3 · system</div><h1 class="h1">Generate</h1>
    <p class="lead">${mine && r.state === "running" ? "Working. Takes appear as they finish; you can start listening once a few are in." : done ? "Finished. Go to Compare to listen and pick." : "Start the run when you're ready."}</p></div>
    <div class="cols"><div class="panel" style="display:flex;flex-direction:column;gap:.9rem">
      ${stages.map((s, i) => { const st = done || (at > i) ? "done" : at === i ? "now" : "wait";
        return `<div class="row"><span class="dot" style="background:${st === "done" ? "var(--voice)" : st === "now" ? "var(--accent)" : "var(--line2)"};${st === "now" ? "box-shadow:0 0 .7rem var(--accent)" : ""}"></span><span style="${st === "wait" ? "color:var(--mute)" : ""}">${s[1]}</span></div>`; }).join("")}
      <div class="bar"><i style="width:${(100 * ready) / j.takes.length}%"></i></div><div class="mono small mute">${ready} / ${j.takes.length} takes</div>
      ${r.state === "error" && mine ? `<div class="err">${esc(r.error)}</div>` : ""}
      <div class="row">${r.state === "running" ? "" : `<button class="btn primary" data-act="run">${ready ? "Resume / finish run" : "Start run"}</button>`}
      <button class="btn" data-go="compare" ${ready ? "" : "disabled"}>Compare →</button></div></div>
    <div class="panel"><div class="clips">${j.takes.map((t) => `<div class="clip" style="--col:${ENG[t.engine][2]};opacity:${t.ready ? 1 : .35}">
      <span class="row small" style="flex-wrap:nowrap"><strong class="trunc" title="${esc(j.parts[t.part].label)} · ${esc(t.label)}">${esc(j.parts[t.part].label)} · ${esc(t.label)}</strong><span class="spacer"></span><span class="tag ${ENG[t.engine][1]}">${ENG[t.engine][0]}</span></span>
      ${t.ready ? `<canvas class="wave" data-wave="t:${j.id}:${t.id}" data-color="${ENG[t.engine][2]}"></canvas>` : `<span class="small mute" style="height:2.2rem">waiting…</span>`}</div>`).join("")}</div></div></div></div>`;
}

/* ---------------- Compare ---------------- */
function partTakes() { return S.job.takes.filter((t) => t.part === S.part && t.ready); }
function partAll() { return S.job.takes.filter((t) => t.part === S.part); }   // ready and still rendering
const SCORE_TIP = { words: "Word accuracy: how closely Whisper's transcript of this take matches your script.", voice: "Voice match: how alike this take sounds to the reference speaker (speaker check). Accent isn't scored; judge it by ear." };
/* scores live on each take, labelled in plain words; shown as % so they read the same everywhere */
function scores(x, compact) {
  const s = x.scores;
  if (!s) return `<span class="sc none small mute">${!S.boot.engines.score.installed ? "Not scored (Whisper not installed)" : x.ready ? "Scoring…" : ""}</span>`;
  return `<span class="sc ${compact ? "compact" : ""}">${[["words", compact ? "Words" : "Word accuracy", "var(--words)"], ["voice", compact ? "Voice" : "Voice match", "var(--voice)"]].map(([k, l, c]) =>
    `<span class="scm" title="${SCORE_TIP[k]}"><span class="scl">${l}</span><span class="scb"><i style="width:${Math.round(s[k] * 100)}%;background:${c}"></i></span><span class="mono scv">${Math.round(s[k] * 100)}%</span></span>`).join("")}</span>`;
}
function pendingNote() { const n = partAll().length - partTakes().length; return n ? `<span class="small mute">${n} still rendering</span>` : ""; }
function curTake() { const ts = partTakes(); if (S.sel >= ts.length) S.sel = 0; return ts[S.sel]; }
const tkey = (t) => `t:${S.job.id}:${t.id}`;
const pct = (x) => (x == null ? "—" : `${Math.round(x * 100)}%`);
const num = (x) => (x == null ? "—" : x.toFixed(2));
function partsBar() {
  const j = S.job;
  return j.parts.length > 1 ? `<div class="parts" role="group" aria-label="Part">${j.parts.map((p, i) => `<button data-part="${i}" aria-pressed="${i === S.part}" title="${esc(p.label)}"><span class="trunc">${esc(p.label)}</span>${j.picks[i] ? " ✓" : ""}</button>`).join("")}</div>` : "";
}
function actionBtns(t) {
  const picked = S.job.picks[S.part] === t?.id;
  return `<button class="btn" data-ab="1" title="A/B against the reference (A)">A/B reference</button>
    <button class="btn" data-act="more" ${S.run?.state === "running" ? "disabled" : ""}>More takes</button>
    <button class="btn primary" data-act="pick" ${t ? "" : "disabled"}>${picked ? "Picked ✓" : "Pick this take"}</button>`;
}
function chunkTip() {
  return S.job && S.job.parts.length > 1 ? `<span class="note small" title="Takes with the same number share a seed across parts">Tip: picking the same take number in each part may help keep the delivery consistent; trust your ear.</span>` : "";
}
function pageCompare() {
  const t = curTake();
  if (!t) return `<div class="page"><h1 class="h1">Compare</h1>${partsBar()}<p class="lead">No takes ready for this part yet.</p></div>`;
  return ({ grade: cmpGrade, reel: cmpReel, signal: cmpSignal, booth: cmpBooth })[S.boot.settings.skin](t);
}
function playBtn(key, big) { const on = S.playing === key && !player.paused; return `<button class="btn round ${big ? "primary" : ""}" data-play="${key}" aria-label="${on ? "Pause" : "Play"}">${on ? "❚❚" : "▶"}</button>`; }
function fmt(t) { if (!isFinite(t) || t < 0) t = 0; const m = Math.floor(t / 60), s = t - m * 60; return `${m}:${s.toFixed(1).padStart(4, "0")}`; }
function timeText(key) { const dur = S.playing === key && isFinite(player.duration) ? player.duration : (PEAKS_DONE[key]?.duration || 0); return `${fmt(S.playing === key ? player.currentTime : 0)} / ${fmt(dur)}`; }
/* the same transport everywhere audio plays: start, back 5 s, play/pause, forward 5 s, time */
function transport(key, o = {}) {
  return `<span class="tp"><button class="btn round sm" data-seek="${key}" data-to="0" aria-label="Back to start" title="Back to start">⏮</button>
    <button class="btn round sm" data-seek="${key}" data-rel="-5" aria-label="Back 5 seconds" title="Back 5 s">−5</button>${playBtn(key, o.big)}
    <button class="btn round sm" data-seek="${key}" data-rel="5" aria-label="Forward 5 seconds" title="Forward 5 s">+5</button>
    <span class="mono small mute" data-time="${key}">${timeText(key)}</span></span>`;
}
function hint() { return `<span class="note">Accent isn't scored. Judge it by ear. <span class="kbd">Space</span> play · <span class="kbd">←</span><span class="kbd">→</span> takes · <span class="kbd">⇧←→</span> ±5 s · <span class="kbd">A</span> A/B · <span class="kbd">Enter</span> pick</span>`; }
function cmpGrade(t) {
  const j = S.job, ts = partTakes(), all = partAll(), sc = t.scores || {};
  return `<div class="cmp grade">
    <div class="takes"><div class="row" style="padding:.8rem .9rem;border-bottom:1px solid var(--line)"><span class="kicker" style="color:var(--mute)">Takes · ${all.length}</span><span class="spacer"></span>${pendingNote()}</div>
      ${j.parts.length > 1 ? `<div style="padding:.6rem .9rem">${partsBar()}</div>` : ""}
      ${all.map((x) => { const i = ts.indexOf(x); return i < 0
        ? `<div class="item pending"><span class="dot" style="background:var(--line2)"></span><span class="grow"><strong class="trunc">${esc(x.label)}</strong><span class="small mute trunc">${ENG[x.engine][0]} · rendering…</span></span></div>`
        : `<button class="item take" data-sel="${i}" aria-selected="${i === S.sel}"><span class="dot" style="background:${ENG[x.engine][2]}"></span>
        <span class="grow"><span class="row" style="gap:.4rem;flex-wrap:nowrap"><strong class="trunc" title="${esc(x.label)}">${esc(x.label)}</strong>${j.picks[S.part] === x.id ? '<span class="picked">PICKED</span>' : ""}</span>
        <span class="small mute trunc">${ENG[x.engine][0]}</span>${scores(x)}</span></button>`; }).join("")}</div>
    <div class="stage"><div class="row small mute" style="justify-content:space-between"><span>REFERENCE</span>${transport("v:" + j.voice_id)}</div>
      <canvas class="wave" data-wave="v:${j.voice_id}" data-color="var(--ref)" style="height:4rem;opacity:.7"></canvas>
      <div class="row small mute" style="margin-top:.6rem"><span class="trunc">${esc(t.label.toUpperCase())} · ${ENG[t.engine][0].toUpperCase()}</span></div>
      <canvas class="wave" data-wave="${tkey(t)}" data-color="${ENG[t.engine][2]}" style="height:7rem"></canvas>
      <p class="wrap" style="font-size:1.05rem;color:var(--text);max-width:52rem;margin:.4rem 0 0">“${esc(j.parts[t.part].text)}”</p>
      ${sc.heard ? `<p class="note wrap" style="margin:0;max-width:52rem" title="${SCORE_TIP.words}"><b>Whisper heard:</b> ${esc(sc.heard)}</p>` : ""}</div>
    <div class="transport actions">${transport(tkey(t), { big: 1 })}${actionBtns(t)}<span class="spacer"></span>${chunkTip() || '<span class="note small">Accent: judge by ear</span>'}</div></div>`;
}
function cmpReel(t) {
  const j = S.job, ts = partTakes(), all = partAll();
  const clip = (x) => { const i = ts.indexOf(x);
    if (i < 0) return `<div class="clip pending" style="--col:${ENG[x.engine][2]}"><span class="small"><strong class="trunc">${esc(x.label)}</strong></span><span class="small mute">rendering…</span></div>`;
    return `<button class="clip" data-sel="${i}" aria-selected="${i === S.sel}" style="--col:${ENG[x.engine][2]}">
    <span class="row small" style="flex-wrap:nowrap"><strong class="trunc" title="${esc(x.label)}">${esc(x.label)}</strong>${j.picks[S.part] === x.id ? "<span>✓</span>" : ""}</span>
    <canvas class="wave" data-wave="${tkey(x)}" data-color="${i === S.sel ? "var(--bg)" : ENG[x.engine][2]}"></canvas>${scores(x, true)}</button>`; };
  const track = (id, name, sub, col, list) => `<div class="track"><div class="head"><span class="badge" style="color:${col};border-color:${col}">${id}</span><span style="min-width:0"><strong>${name}</strong><br><span class="small mute">${sub}</span></span></div><div class="clips">${list}</div></div>`;
  return `<div class="cmp reel"><div class="row"><h1 class="h1">Compare · Pick</h1><span class="kicker trunc" style="max-width:24rem">${esc(j.parts[S.part].label)} · ${all.length} takes</span>${pendingNote()}<span class="spacer"></span>${partsBar()}</div>
    ${track("REF", "Reference", "operator's clip", "var(--ref)", `<button class="clip" data-play="v:${j.voice_id}" style="--col:var(--ref)"><span class="small"><strong>Reference clip</strong></span><canvas class="wave" data-wave="v:${j.voice_id}" data-color="var(--ref)"></canvas></button>`)}
    ${track("V1", "Qwen3-TTS", "full reference", "var(--qwen)", all.filter((x) => x.engine === "qwen").map(clip).join(""))}
    ${all.some((x) => x.engine === "cbx") ? track("V2", "Chatterbox", "three settings", "var(--cbx)", all.filter((x) => x.engine === "cbx").map(clip).join("")) : ""}
    <div class="actions">${transport(tkey(t), { big: 1 })}<span style="color:#F0509A" class="small">Accent isn't scored · the operator's ear decides.</span><span class="spacer"></span>${actionBtns(t)}</div>${chunkTip()}</div>`;
}
function cmpSignal(t) {
  const j = S.job, ts = partTakes();
  return `<div class="cmp signal"><div class="row"><span class="kicker trunc" style="max-width:24rem">CH ${String(S.sel + 1).padStart(2, "0")} · ${esc(j.parts[S.part].label)}</span>${pendingNote()}<span class="spacer"></span>${partsBar()}</div>
    <div class="scope"><span class="lab trunc" style="left:.8rem;max-width:70%">${esc((ENG[t.engine][0] + " · " + t.label).toUpperCase())}</span><span class="lab" style="right:.8rem;color:var(--accent)">REF ░ OVERLAY</span>
      <canvas class="wave" data-wave="v:${j.voice_id}" data-color="#3A3F38" data-mirror="1"></canvas><canvas class="wave" data-wave="${tkey(t)}" data-color="var(--accent)" data-mirror="1"></canvas></div>
    <div class="actions">${transport(tkey(t), { big: 1 })}<span class="small mute">REF</span>${playBtn("v:" + j.voice_id)}<span class="spacer"></span>${actionBtns(t)}</div>
    <div class="strips">${partAll().map((x) => { const i = ts.indexOf(x); return i < 0 ? `<div class="strip pending"><span class="small mute">${x.engine === "qwen" ? "QWN" : "CBX"} · rendering…</span><span class="trunc" style="color:var(--text)">${esc(x.label)}</span></div>` : `<button class="strip" data-sel="${i}" aria-selected="${i === S.sel}">
      <span class="row small" style="justify-content:space-between;width:100%"><span class="mute">CH ${String(i + 1).padStart(2, "0")}</span><span class="tag ${ENG[x.engine][1]}">${x.engine === "qwen" ? "QWN" : "CBX"}</span></span>
      <span class="trunc" style="font-family:var(--font-display);font-size:1.05rem;color:var(--text);width:100%" title="${esc(x.label)}">${esc(x.label)}${j.picks[S.part] === x.id ? " ✓" : ""}</span>
      ${x.scores ? `<span class="vu"><span title="${SCORE_TIP.words}"><i style="height:${x.scores.words * 100}%;background:var(--words)"></i>Words</span><span title="${SCORE_TIP.voice}"><i style="height:${x.scores.voice * 100}%;background:var(--voice)"></i>Voice</span></span>
      <span class="row small" style="justify-content:space-around;width:100%"><span>${pct(x.scores.words)}</span><span>${pct(x.scores.voice)}</span></span>` : scores(x, true)}</button>`; }).join("")}</div>
    <div class="row">${hint()}${chunkTip()}</div></div>`;
}
function cmpBooth(t) {
  const j = S.job, ts = partTakes(), sc = t.scores || {};
  return `<div class="cmp booth"><div class="hero">
    <div class="row"><span class="tally booth-tally ${S.playing && !player.paused ? "on" : ""}"></span><span class="kicker" style="color:var(--accent)">Listening</span><span class="spacer"></span>${partsBar()}</div>
    <div class="row" style="align-items:baseline;gap:1.4rem"><span class="bignum">${String(S.sel + 1).padStart(2, "0")} / ${String(ts.length).padStart(2, "0")}</span>
      <span style="min-width:0;flex:1"><span class="wrap" style="font-size:1.9rem;font-weight:300">${esc(t.label)}</span>${j.picks[S.part] === t.id ? ' <span class="picked">PICKED</span>' : ""}<br><span style="color:${ENG[t.engine][2]};letter-spacing:.08em">${ENG[t.engine][0]}</span></span></div>
    <canvas class="wave" data-wave="${tkey(t)}" data-color="#EFE7DF" data-dim="#4A3F36" data-bars="110"></canvas>
    <div class="quote wrap">“${esc(j.parts[t.part].text)}”</div>
    <div class="row" style="gap:2rem;max-width:44rem">${scores(t)}<span class="small mute">Accent · your ear</span></div>${pendingNote()}${chunkTip()}</div>
    <div class="actions">${transport(tkey(t), { big: 1 })}<span style="width:1.6rem"></span>
      <button class="btn sm" data-step="-1" aria-label="Previous take">‹ Take</button><span class="pips">${ts.map((x, i) => `<i class="${i === S.sel ? "on" : ""}" style="${i === S.sel ? `background:${ENG[x.engine][2]}` : ""}"></i>`).join("")}</span><button class="btn sm" data-step="1" aria-label="Next take">Take ›</button><span class="spacer"></span>
      <button class="btn" data-play="v:${j.voice_id}">Hear reference</button>${actionBtns(t).replace(/<button class="btn" data-ab="1"[^>]*>A\/B reference<\/button>/, "")}</div></div>`;
}

/* ---------------- Deliver ---------------- */
function exportOpts() { if (!S.exportOpts || S.exportOpts.job !== S.jobId) S.exportOpts = { job: S.jobId, separate: true, joined: S.job.parts.length > 1 }; return S.exportOpts; }
function pageDeliver() {
  const j = S.job, s = S.boot.settings, all = j.parts.every((_, i) => j.picks[i]), o = exportOpts(), many = j.parts.length > 1;
  const nPicked = Object.keys(j.picks).length;
  return `<div class="page"><div><div class="kicker">Step 4 · operator</div><h1 class="h1">Deliver</h1>
    <p class="lead">Export the picked take for each part as a clearly named WAV file, and${many ? "" : " optionally"} join them into one file, ready for the edit.</p></div>
    <div class="panel" style="display:flex;flex-direction:column;gap:1rem">
      ${many ? `<div class="row"><button class="btn ${S.seq ? "" : "primary"}" data-act="play-all" ${nPicked ? "" : "disabled"}>${S.seq ? "■ Stop" : "▶ Play all picks"}</button><span class="note">Plays every picked part in order with the same pauses as the joined file, so you can hear the joins.</span></div>` : ""}
      ${j.parts.map((p, i) => { const t = j.takes.find((x) => x.id === j.picks[i]); const now = S.seq && t && S.playing === tkey(t);
      return `<div class="row deliv ${now ? "now" : ""}"><strong class="trunc" style="width:12rem" title="${esc(p.label)}">${esc(p.label)}</strong>${t ? `${transport(tkey(t))}<span class="tag ${ENG[t.engine][1]}">${ENG[t.engine][0]}</span><span class="trunc" style="max-width:14rem" title="${esc(t.label)}">${esc(t.label)}</span>
        <div style="flex:1;min-width:10rem"><canvas class="wave" data-wave="${tkey(t)}" data-color="${ENG[t.engine][2]}" style="height:2.6rem"></canvas></div>
        <button class="btn sm" data-part-go="${i}">Re-pick</button>` : `<span class="mute">Nothing picked yet</span><button class="btn sm" data-part-go="${i}">Pick in Compare</button>`}</div>`; }).join("")}</div>
    <div class="panel" style="display:flex;flex-direction:column;gap:.8rem">
      <div class="row"><div class="field" style="flex:1;min-width:12rem"><label>Export folder</label><div class="mono small wrap">${esc(s.export_dir)}</div></div><button class="btn" data-act="choose-dir">Change…</button></div>
      <label class="switch"><input type="checkbox" id="xsep" ${o.separate ? "checked" : ""}><span>Separate file for each part</span></label>
      <label class="switch"><input type="checkbox" id="xjoin" ${o.joined ? "checked" : ""}><span>One joined file of the whole piece<br><span class="note">Trims silence at each part's edges, matches loudness across parts, and adds a short pause inside a paragraph, a longer one at a paragraph end, and a longer one again between separate parts.${all ? "" : " Needs a pick for every part."}</span></span></label>
      <div class="row"><button class="btn primary" data-act="export" ${nPicked && (o.separate || o.joined) ? "" : "disabled"}>Export</button></div></div>
    ${many ? longGuide(false) : ""}
    ${S.exportResult ? `<div class="panel"><div class="row"><span class="dot" style="background:var(--voice)"></span><strong>Exported ${S.exportResult.files.length} file(s)</strong><span class="spacer"></span><button class="btn" data-act="open-dir">Open folder</button></div>
      <div class="mono small mute wrap" style="margin-top:.6rem">${S.exportResult.files.map(esc).join("<br>")}</div></div>` : ""}</div>`;
}

/* play every picked part in order with the joined file's pauses */
const PAUSE_JS = { sentence: 350, para: 800, part: 1000 };
function playAll() {
  const j = S.job, seq = j.parts.map((p, i) => ({ p, t: j.takes.find((x) => x.id === j.picks[i]) })).filter((x) => x.t);
  if (!seq.length) return;
  let k = 0; S.seq = true; render();
  const next = () => {
    if (!S.seq) return;
    if (k >= seq.length) { stopAll(); return; }
    const { t } = seq[k]; const key = tkey(t);
    load(key); whenReady(() => { player.currentTime = 0; player.play().catch(() => {}); render(); });
    player.onended = () => {
      const cur = seq[k], nx = seq[k + 1]; k++;
      const same = nx && cur.p.group && cur.p.group === nx.p.group;
      setTimeout(next, nx ? (same ? PAUSE_JS[cur.p.brk || "para"] : PAUSE_JS.part) : 0);
    };
  };
  next();
}
function stopAll() { S.seq = false; player.onended = null; player.pause(); render(); }

/* ---------------- Settings ---------------- */
function pageSettings() {
  const s = S.boot.settings, e = S.boot.engines, g = S.boot.gpu, busy = S.run?.state === "running";
  return `<div class="page"><div><div class="kicker">Settings</div><h1 class="h1">Look and behaviour</h1></div>
    <div class="panel" style="display:flex;flex-direction:column;gap:.9rem"><strong>Skin</strong>
      <div class="skins">${Object.entries(SKINS).map(([id, [nm, sub]]) => `<button class="skin" data-skin="${id}" aria-pressed="${s.skin === id}" aria-label="Use the ${nm} skin">
        <span class="pvwrap">${previewHTML(id)}</span>
        <span class="nm"><strong>${nm}${s.skin === id ? " · in use" : ""}</strong><span class="small mute">${sub}</span></span></button>`).join("")}</div>
      <span class="note">Each preview is the real Compare screen drawn in that skin.</span></div>
    <div class="panel" style="display:flex;flex-direction:column;gap:.6rem"><label for="scale"><strong>Interface size</strong> <span class="mono small mute" id="scalev">${Math.round(s.ui_scale * 100)}%</span></label>
      <input id="scale" type="range" min="0.8" max="1.6" step="0.05" value="${s.ui_scale}" style="accent-color:var(--accent)">
      <span class="note">Works on top of Windows display scaling. Raise it on large or distant screens; lower it to fit more on a small laptop.</span></div>
    <div class="panel" style="display:flex;flex-direction:column;gap:.8rem"><strong>Defaults for new jobs</strong>
      <div class="row"><label for="dtakes">Qwen takes per part</label><input class="input mono" id="dtakes" type="number" min="1" max="8" value="${s.takes_per_part}" style="width:6rem"></div>
      <label class="switch"><input type="checkbox" id="dcbx" ${s.include_chatterbox ? "checked" : ""}><span>Include Chatterbox takes by default</span></label>
      <label class="switch"><input type="checkbox" id="dfree" ${s.free_gpu_before_run ? "checked" : ""}><span>Free GPU memory held by other local apps (e.g. Ollama) before each run<br><span class="note">${S.boot.ollama?.length ? `Currently loaded: ${esc(S.boot.ollama.join(", "))}` : "Nothing else is holding the GPU right now."}</span></span></label></div>
    <div class="panel" style="display:flex;flex-direction:column;gap:.7rem"><strong>Engines</strong>
      <div class="mono small mute">${g.ok ? `${esc(g.name)} · ${g.used_gb}/${g.total_gb} GB in use` : esc(g.error || "No GPU")}</div>
      <div class="erows">${Object.entries(e).map(([n, x]) => `<div class="erow"><span class="row" style="flex-wrap:nowrap;gap:.6rem"><span class="dot" style="background:${x.installed ? "var(--voice)" : "var(--line2)"}"></span><span class="trunc">${esc(x.title)}</span></span>
        <div class="estat">${engStatus(n)}</div>
        <button class="btn sm" data-install="${n}" ${busy ? "disabled" : ""}>${x.installed ? "Repair" : "Install"}</button></div>`).join("")}</div></div>
    ${updatesPanel(busy)}
    <p class="note">Original Accent runs entirely on this PC. Only clone voices you have permission to use.</p></div>`;
}

/* ---------------- skin previews ----------------
   The real top bar, page bar and Compare layout, rendered with sample takes inside a
   1280x720 frame and scaled to the card, so what you see is what the skin looks like. */
const SAMPLE = (() => {
  const mk = (id, engine, label, w, v) => ({ id, part: 0, engine, config: engine === "qwen" ? "full" : "x", label, ready: true, scores: { words: w, voice: v } });
  return { id: "sample", name: "Launch narration", voice_id: "sample", include_chatterbox: true, picks: {},
    parts: [{ label: "Part 1", text: "Every frame matters when you're this close to the finish line." }, { label: "Part 2", text: "" }],
    takes: [mk("q1", "qwen", "Take 1", .94, .78), mk("q2", "qwen", "Take 2", .92, .77), mk("q3", "qwen", "Take 3", .95, .79),
      mk("c1", "cbx", "Default", .93, .79), mk("c2", "cbx", "Low guidance", .91, .8), mk("c3", "cbx", "Turbo", .9, .76)] };
})();
function previewHTML(skin) {
  const keep = { job: S.job, part: S.part, sel: S.sel, page: S.page, playing: S.playing, skin: S.boot.settings.skin };
  Object.assign(S, { job: SAMPLE, part: 0, sel: 0, page: "compare", playing: null }); S.boot.settings.skin = skin;
  let html;
  try {
    html = `<span class="pv" data-sk="${skin}"><span class="shell" style="display:grid"><span class="top">${topHTML()}</span><span class="nav">${navHTML()}</span><span class="main">${pageCompare()}</span></span></span>`;
  } finally { Object.assign(S, { job: keep.job, part: keep.part, sel: keep.sel, page: keep.page, playing: keep.playing }); S.boot.settings.skin = keep.skin; }
  // buttons can't sit inside the card's button: keep their look, drop their behaviour
  return html.replace(/<button/g, "<span").replace(/<\/button>/g, "</span>").replace(/ data-(go|sel|play|act|part|step|ab)="[^"]*"/g, "");
}
function fitPreviews() { document.querySelectorAll(".pvwrap").forEach((w) => { const pv = w.firstElementChild; if (pv) pv.style.transform = `scale(${w.clientWidth / 1280})`; }); }

function updatesPanel(busy) {
  const u = S.updates, s = S.boot.settings;
  const rows = u ? Object.entries(u.engines || {}).map(([n, e]) => {
    const up = Object.fromEntries(e.packages.map((p) => [p.name, p.latest || "newer"]));
    const items = [...e.packages.map((p) => `${esc(p.name)} ${esc(p.version)} → ${esc(p.latest || "newer")}`), ...e.models.map((m) => `model ${esc(m.name.split("/")[1])} (newer files)`)];
    // every package with its installed version, whether or not there's an update; the new version beside the ones that have one
    const inst = (e.installed || []).map((p) => `<span class="nw">${esc(p.name)}\u00a0${esc(p.version)}${up[p.name] ? `<strong> → ${esc(up[p.name])}</strong>` : ""}</span>`);
    const extra = e.packages.filter((p) => !(e.installed || []).some((i) => i.name === p.name)).map((p) => `<span class="nw">${esc(p.name)} ${esc(p.version)}<strong> → ${esc(p.latest || "newer")}</strong></span>`);
    const models = e.models.map((m) => `<span class="nw">model ${esc(m.name.split("/")[1])}<strong> → newer files</strong></span>`);
    const status = e.error ? esc(e.error) : items.length ? `${items.length} update${items.length > 1 ? "s" : ""} available` : "Up to date";
    return `<div class="row" style="align-items:flex-start"><span class="dot" style="margin-top:.45em;background:${items.length ? "var(--accent)" : "var(--voice)"}"></span>
      <span style="min-width:12rem">${esc(e.title)}<br><span class="small mute">${status}</span></span>
      <span class="small mute wrap" style="flex:1;min-width:10rem;display:flex;flex-wrap:wrap;gap:.2rem .9rem">${[...inst, ...extra, ...models].join("")}</span>
      ${items.length ? `<button class="btn sm" data-upgrade="${n}" ${busy ? "disabled" : ""}>Update</button>` : ""}</div>`; }).join("") : "";
  return `<div class="panel" style="display:flex;flex-direction:column;gap:.7rem"><div class="row"><strong>Updates</strong><span class="spacer"></span>
      <span class="small mute">${u?.checked ? `Last checked ${esc(u.checked.replace("T", " "))}` : "Not checked yet"}</span>
      <button class="btn sm" data-act="check-updates" ${busy ? "disabled" : ""}>Check now</button></div>
    ${rows}
    <label class="switch"><input type="checkbox" id="dupd" ${s.check_updates ? "checked" : ""}><span>Check for engine updates once a day<br><span class="note">Only version information is fetched from PyPI and Hugging Face. Updating an engine reinstalls it with its newest compatible packages and model files; if an update ever misbehaves, use Repair to reinstall.</span></span></label>
    <p class="note" style="margin:0">Original Accent ${esc(S.boot.version || "")}. Checking for new versions of the app itself will switch on once it's published on GitHub.</p></div>`;
}

/* ---------------- waveforms ---------------- */
const PEAKS = {}, PEAKS_DONE = {};
function samplePeaks(key) { let h = 0; for (const c of key) h = (h * 31 + c.charCodeAt(0)) % 997; return { duration: 6, peaks: [...Array(600)].map((_, i) => +(0.08 + Math.abs(Math.sin(i * 0.031 + h) * Math.cos(i * 0.0117 + h / 7)) * 0.92).toFixed(3)) }; }
async function peaksFor(key) {
  if (key.includes(":sample")) return (PEAKS_DONE[key] = samplePeaks(key));
  if (PEAKS[key]) return PEAKS[key];
  const [k, a, b] = key.split(":");
  PEAKS[key] = (k === "v" ? api("voice_peaks", { id: a, n: 600 }) : k === "f" ? api("full_peaks", { id: a, n: 1600 }) : api("take_peaks", { job: a, take: b, n: 600 }))
    .then((p) => { PEAKS_DONE[key] = p; document.querySelectorAll(`[data-time="${key}"]`).forEach((el) => (el.textContent = timeText(key))); return p; });
  return PEAKS[key];
}
function cssColor(c, el = document.body) { if (!c.startsWith("var(")) return c; return getComputedStyle(el).getPropertyValue(c.slice(4, -1)).trim() || "#888"; }
async function drawWave(cv) {
  const key = cv.dataset.wave; let p;
  try { p = await peaksFor(key); } catch { return; }
  const dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight || 40;
  if (!w) return;
  cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
  const g = cv.getContext("2d"); g.scale(dpr, dpr); g.clearRect(0, 0, w, h);
  const bars = +(cv.dataset.bars || Math.max(24, Math.floor(w / 4))), col = cssColor(cv.dataset.color || "var(--accent)", cv);
  const dim = cv.dataset.dim ? cssColor(cv.dataset.dim, cv) : null, src = p.peaks || [];
  const prog = S.playing === key && player.duration ? player.currentTime / player.duration : -1;
  const bw = w / bars;
  for (let i = 0; i < bars; i++) {
    const v = src.length ? src[Math.floor((i / bars) * src.length)] : 0.1, bh = Math.max(1.5, v * h * 0.95);
    g.fillStyle = prog >= 0 && i / bars > prog ? (dim || col) : col;
    g.globalAlpha = prog >= 0 && i / bars > prog && !dim ? 0.45 : 1;
    g.fillRect(i * bw + bw * 0.15, (h - bh) / 2, Math.max(1, bw * 0.7), bh);
  }
  g.globalAlpha = 1;
  if (cv.dataset.trim && S.trim && p.duration) {           // section: dim outside, handles at the edges
    const xs = (S.trim.s / p.duration) * w, xe = (S.trim.e / p.duration) * w, acc = cssColor("var(--accent)", cv);
    g.fillStyle = "rgba(0,0,0,.6)"; g.fillRect(0, 0, xs, h); g.fillRect(xe, 0, w - xe, h);
    g.fillStyle = acc; g.globalAlpha = 0.12; g.fillRect(xs, 0, xe - xs, h); g.globalAlpha = 1;
    for (const x of [xs, xe]) { g.fillRect(x - 1.5, 0, 3, h); g.fillRect(x - 5, 0, 10, 12); g.fillRect(x - 5, h - 12, 10, 12); }
  }
  if (prog >= 0) { g.fillStyle = cssColor(cv.dataset.trim ? "var(--text)" : "var(--accent)", cv); g.fillRect(prog * w - 1, 0, 2, h); }
}
function drawAll() { document.querySelectorAll("canvas.wave").forEach(drawWave); }
new ResizeObserver(() => requestAnimationFrame(() => { fitPreviews(); drawAll(); })).observe(document.body);
window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`).addEventListener?.("change", () => requestAnimationFrame(drawAll));

/* ---------------- playback ----------------
   One audio element. Any waveform is a scrub bar: click or drag to move the playhead,
   scroll to step through; transports add start / -5 s / +5 s and a time readout. */
const player = $("#player");
function load(key) { if (S.playing !== key) { player.src = media(key); S.playing = key; S.stopAt = null; } }
function whenReady(fn) { if (player.readyState >= 1 && isFinite(player.duration)) fn(); else player.addEventListener("loadedmetadata", fn, { once: true }); }
function play(key, keepPos) {
  if (S.playing === key && !player.paused) { player.pause(); return; }
  const frac = keepPos && S.playing && S.playing !== key && player.duration ? player.currentTime / player.duration : null;
  load(key);
  if (frac != null) whenReady(() => { player.currentTime = frac * player.duration; });
  player.play().catch(() => {});
}
function seek(key, { frac, rel, to }) {
  load(key);
  whenReady(() => {
    const d = player.duration, t = to != null ? to : frac != null ? frac * d : player.currentTime + rel;
    player.currentTime = Math.max(0, Math.min(d - 0.02, t)); syncPlayback();
  });
}
function syncPlayback() {
  const on = !player.paused;
  document.querySelectorAll("[data-play]").forEach((b) => {
    if (b.closest(".pv") || !b.classList.contains("round")) return;
    const me = b.dataset.play === S.playing && on; b.textContent = me ? "❚❚" : "▶"; b.setAttribute("aria-label", me ? "Pause" : "Play");
  });
  document.querySelectorAll("[data-time]").forEach((el) => { if (!el.closest(".pv")) el.textContent = timeText(el.dataset.time); });
  if (S.playing) document.querySelectorAll(`canvas.wave[data-wave="${S.playing}"]`).forEach(drawWave);
  document.querySelectorAll(".booth-tally").forEach((el) => el.classList.toggle("on", on));
}
player.addEventListener("play", () => { syncPlayback(); tick(); });
["pause", "seeked", "ended", "loadedmetadata"].forEach((ev) => player.addEventListener(ev, syncPlayback));
function tick() {
  if (player.paused) return;
  if (S.stopAt != null && player.currentTime >= S.stopAt) { player.pause(); S.stopAt = null; }
  syncPlayback(); requestAnimationFrame(tick);
}
function ab() { const t = curTake(); if (!t) return; const tk = tkey(t), rk = "v:" + S.job.voice_id; play(S.playing === tk ? rk : tk, true); }
let drag = null;
function waveFrac(e, r) { return Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)); }
function nearHandle(cv, x, r) {
  const dur = PEAKS_DONE[cv.dataset.wave]?.duration;
  if (!cv.dataset.trim || !dur || !S.trim) return null;
  const xs = (S.trim.s / dur) * r.width, xe = (S.trim.e / dur) * r.width;
  return Math.abs(x - xs) < 10 ? "s" : Math.abs(x - xe) < 10 ? "e" : null;
}
document.addEventListener("pointerdown", (e) => {
  const cv = e.target.closest?.("canvas.wave"); if (!cv || cv.closest(".pv")) return;
  const r = cv.getBoundingClientRect(), key = cv.dataset.wave, h = nearHandle(cv, e.clientX - r.left, r);
  drag = { cv, key, r, mode: h || "seek", dur: PEAKS_DONE[key]?.duration || 0 };
  if (!h) seek(key, { frac: waveFrac(e, r) });
  cv.setPointerCapture(e.pointerId); e.preventDefault();
});
document.addEventListener("pointermove", (e) => {
  if (!drag) {
    const cv = e.target.closest?.("canvas.wave");
    if (cv && cv.dataset.trim) { const r = cv.getBoundingClientRect(); cv.style.cursor = nearHandle(cv, e.clientX - r.left, r) ? "ew-resize" : ""; }
    return;
  }
  const f = waveFrac(e, drag.r);
  if (drag.mode === "seek") seek(drag.key, { frac: f });
  else {
    const t = +(f * drag.dur).toFixed(2);
    if (drag.mode === "s") S.trim.s = Math.max(0, Math.min(t, S.trim.e - 1)); else S.trim.e = Math.min(drag.dur, Math.max(t, S.trim.s + 1));
    S.trim.reason = null; updateTrimFields(); drawWave(drag.cv);
  }
});
document.addEventListener("pointerup", () => { if (drag && drag.mode !== "seek") $("[data-act=trim]")?.classList.add("primary"); drag = null; });
document.addEventListener("wheel", (e) => {
  const cv = e.target.closest?.("canvas.wave"); if (!cv || cv.closest(".pv")) return;
  e.preventDefault(); seek(cv.dataset.wave, { rel: (e.deltaY || e.deltaX) > 0 ? 1 : -1 });
}, { passive: false });

/* ---------------- events ---------------- */
document.addEventListener("click", (ev) => guard(async () => {
  const b = ev.target.closest("button,[data-skin]"); if (!b) return;
  const d = b.dataset;
  if (d.go) { S.page = d.go; render(); }
  else if (d.voice) { S.voiceId = d.voice; S.trim = null; render(); }
  else if (d.job) { await openJob(d.job); }
  else if (d.play) { play(d.play); }
  else if (d.seek) { seek(d.seek, d.to != null ? { to: +d.to } : { rel: +d.rel }); }
  else if (d.sel != null) { S.sel = +d.sel; render(); if (S.playing?.startsWith("t:")) play(tkey(curTake())); }
  else if (d.step) { const n = partTakes().length; S.sel = (S.sel + +d.step + n) % n; render(); }
  else if (d.part != null) { S.part = +d.part; S.sel = 0; render(); }
  else if (d.partGo != null) { S.part = +d.partGo; S.sel = 0; S.page = "compare"; render(); }
  else if (d.ab) { ab(); }
  else if (d.skin && b.classList.contains("skin")) { S.boot.settings = await api("settings_save", { skin: d.skin }); applySettings(); render(); }
  else if (d.upgrade) { await api("setup_install", { engines: [d.upgrade], upgrade: true }); S.run = await api("run_state"); render(); }
  else if (d.install) { await api("setup_install", { engines: [d.install] }); S.run = await api("run_state"); render(); }
  else if (d.delpart != null) { draft().parts.splice(+d.delpart, 1); render(); }
  else if (d.split != null) { const n = splitPart(+d.split); toast(n ? `Split into ${n} chunks at paragraph and sentence ends.` : "This part can't be split any further."); render(); }
  else if (d.merge != null) { mergeGroup(d.merge); render(); }
  else if (d.eng) { /* checkbox inside label */ }
  else if (d.act) await act(d.act);
}));
async function act(a) {
  const v = curVoice();
  if (a === "skip-setup") { S.setupDismissed = true; render(); }
  else if (a === "install") { const sel = Object.entries(setupSel()).filter(([n, on]) => on || n === "qwen").map(([n]) => n); await api("setup_install", { engines: sel }); S.run = await api("run_state"); render(); }
  else if (a === "transcribe") { await saveVoice(); await api("voice_transcribe", { id: v.id }); S.run = await api("run_state"); render(); }
  else if (a === "save-voice") { await saveVoice(); toast("Voice saved"); render(); }
  else if (a === "trim") {
    const T = trimOf(v); if (!(T.e > T.s)) throw new Error("The end of the section must be after the start.");
    if (S.playing === "v:" + v.id) { player.pause(); S.playing = null; }
    const nv = await api("voice_update", { id: v.id, trim: [T.s, T.e] }); delete PEAKS["v:" + v.id]; delete PEAKS_DONE["v:" + v.id]; replaceVoice(nv);
    toast(v.transcript ? "Section applied. If the words changed, update or re-draft the transcript." : "Section applied."); render();
  }
  else if (a === "suggest") { const T = trimOf(v), r = await api("suggest_trim", { id: v.id }); [T.s, T.e] = r.trim; T.reason = r.reason; render(); }
  else if (a === "play-sel") { const T = trimOf(v), key = "f:" + v.id; load(key); whenReady(() => { player.currentTime = T.s; S.stopAt = T.e; player.play().catch(() => {}); }); }
  else if (a === "addpart") { const d = draft(); d.parts.push({ label: `Part ${d.parts.length + 1}`, text: "" }); render(); }
  else if (a === "generate") {
    const d = draft(); const vv = S.boot.voices.find((x) => x.id === d.voice_id);
    if (!vv) throw new Error("Add a voice first."); if (!vv.transcript) throw new Error("That voice has no transcript yet. Add it on the Voice page.");
    const j = await api("job_create", d); S.boot.jobs = await api("jobs"); S.draft = null;
    await openJob(j.id, false); await api("job_run", { id: j.id }); S.run = await api("run_state"); S.page = "generate"; render();
  }
  else if (a === "run") { await api("job_run", { id: S.jobId }); S.run = await api("run_state"); render(); }
  else if (a === "more") { await api("job_more", { id: S.jobId, part: S.part, n: 2 }); S.job = await api("job_get", { id: S.jobId }); S.run = await api("run_state"); S.page = "generate"; render(); }
  else if (a === "pick") { const t = curTake(); S.job = await api("job_pick", { id: S.jobId, part: S.part, take: t.id }); toast(`Picked ${t.label} for ${S.job.parts[S.part].label}`); render(); }
  else if (a === "choose-dir") { const p = await api("choose_folder"); if (p) { S.boot.settings = await api("settings_save", { export_dir: p }); render(); } else if (!window.pywebview) toast("Folder picker is available in the app window."); }
  else if (a === "check-updates") { toast("Checking for updates…"); S.updates = await api("updates_check"); toast(S.updates.any ? "Updates are available." : "Everything is up to date."); render(); }
  else if (a === "split-all") { const d = draft(); let made = 0; for (let i = d.parts.length - 1; i >= 0; i--) if (words(d.parts[i].text) > chunkTarget(d.include_chatterbox)) made += splitPart(i); toast(`Split long parts into ${made} chunks.`); render(); }
  else if (a === "play-all") { if (S.seq) stopAll(); else playAll(); }
  else if (a === "export") { const o = exportOpts(); S.exportResult = await api("job_export", { id: S.jobId, separate: o.separate, joined: o.joined }); render(); }
  else if (a === "open-dir") { await api("open_folder", { path: S.exportResult.folder }); }
}
function replaceVoice(nv) { S.boot.voices = S.boot.voices.map((x) => (x.id === nv.id ? nv : x)); }
async function saveVoice() { const v = curVoice(); if (!v) return; const nv = await api("voice_update", { id: v.id, name: $("#vname").value, transcript: $("#vtx").value }); replaceVoice(nv); }
document.addEventListener("input", (ev) => {
  const t = ev.target, d = S.draft;
  if (t.tagName === "TEXTAREA") autosize(t);
  if (t.id === "jname") draft().name = t.value;
  else if (t.id === "jtakes") draft().takes_per_part = Math.max(1, Math.min(8, +t.value || 1));
  else if (t.dataset.plabel != null) draft().parts[+t.dataset.plabel].label = t.value;
  else if (t.dataset.ptext != null) {
    const i = +t.dataset.ptext; draft().parts[i].text = t.value;
    const wc = $(`[data-wc="${i}"]`), lim = $(`[data-lim="${i}"]`);
    if (wc) wc.textContent = wcText(t.value); if (lim) lim.innerHTML = limitNote(t.value, draft().include_chatterbox);
  }
  else if (t.id === "ts" || t.id === "te") { const v = curVoice(), T = v && trimOf(v); if (T && t.value !== "") { T[t.id === "ts" ? "s" : "e"] = +t.value; T.reason = null; $("#tsel").textContent = trimNote(T); document.querySelectorAll("canvas.wave[data-trim]").forEach(drawWave); } }
  else if (t.id === "scale") { document.documentElement.style.setProperty("--ui-scale", t.value); $("#scalev").textContent = Math.round(t.value * 100) + "%"; }
});
document.addEventListener("change", (ev) => guard(async () => {
  const t = ev.target;
  if (t.dataset.eng) { setupSel()[t.dataset.eng] = t.checked; return; }
  if (t.id === "consent") { S.consent = t.checked; render(); return; }
  if (t.id === "jvoice") draft().voice_id = t.value;
  else if (t.id === "jcbx") { draft().include_chatterbox = t.checked; render(); }
  else if (t.id === "jtakes") render();
  else if (t.id === "scale") S.boot.settings = await api("settings_save", { ui_scale: +t.value });
  else if (t.id === "dtakes") S.boot.settings = await api("settings_save", { takes_per_part: +t.value });
  else if (t.id === "dcbx") S.boot.settings = await api("settings_save", { include_chatterbox: t.checked });
  else if (t.id === "dfree") S.boot.settings = await api("settings_save", { free_gpu_before_run: t.checked });
  else if (t.id === "xsep" || t.id === "xjoin") { exportOpts()[t.id === "xsep" ? "separate" : "joined"] = t.checked; render(); }
  else if (t.id === "dupd") S.boot.settings = await api("settings_save", { check_updates: t.checked });
  else if (t.id === "vname" || t.id === "vtx") await saveVoice();
  else if (t.id === "file") await upload(t.files[0]);
}));
const MAX_UPLOAD = 4 * 1024 ** 3;
async function upload(f) {
  if (!f) return;
  if (!S.consent) throw new Error("Tick “I have the speaker's permission to clone their voice” first.");
  if (f.size > MAX_UPLOAD) throw new Error("That file is over 4 GB. Trim it to the part with the speaker, or export just its audio, then add it.");
  const drop = $("#drop"), url = `/upload?t=${VC_TOKEN}&consent=1&filename=${encodeURIComponent(f.name)}&name=${encodeURIComponent(f.name.replace(/\.[^.]+$/, ""))}`;
  const say = (t) => { if (drop) drop.innerHTML = `<span class="small">${esc(t)}</span>`; };
  say(`Adding ${f.name}…`);
  // XMLHttpRequest rather than fetch: it reports upload progress, which matters for big video files
  const v = await new Promise((res, rej) => {
    const x = new XMLHttpRequest(); x.open("POST", url);
    x.upload.onprogress = (e) => e.lengthComputable && say(`Adding ${f.name} · ${Math.round((100 * e.loaded) / e.total)}%`);
    x.upload.onload = () => say(`Reading the audio from ${f.name}…`);
    x.onload = () => { try { res(JSON.parse(x.responseText)); } catch (e) { rej(e); } };
    x.onerror = () => rej(new Error("The file couldn't be added."));
    x.send(f);
  }).finally(() => setTimeout(() => S.page === "voice" && render(), 0));
  if (v.ok === false) throw new Error(v.error);
  S.boot.voices = await api("voices"); S.voiceId = v.id; S.trim = null; S.consent = false; render();
}
document.addEventListener("dragover", (e) => { const d = e.target.closest?.("#drop"); if (d) { e.preventDefault(); d.classList.add("over"); } });
document.addEventListener("dragleave", (e) => e.target.closest?.("#drop")?.classList.remove("over"));
document.addEventListener("drop", (e) => { const d = e.target.closest?.("#drop"); if (!d) return; e.preventDefault(); guard(() => upload(e.dataTransfer.files[0])); });
document.addEventListener("keydown", (e) => {
  if (/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName)) return;
  if (e.key === "Escape") { $("#errpanel")?.remove(); document.querySelector(".overlay.modal")?.remove(); return; }
  if (S.page === "voice") {
    const v = curVoice(); if (!v) return; const key = S.playing?.startsWith("v:") ? S.playing : "f:" + v.id;
    if (e.key === " ") { e.preventDefault(); play(key); }
    else if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); seek(key, { rel: (e.key === "ArrowRight" ? 1 : -1) * (e.shiftKey ? 5 : 1) }); }
    return;
  }
  if (S.page !== "compare") return;
  const n = partTakes().length; if (!n) return;
  if (e.key === " ") { e.preventDefault(); play(tkey(curTake())); }
  else if ((e.key === "ArrowRight" || e.key === "ArrowLeft") && e.shiftKey) { e.preventDefault(); seek(S.playing || tkey(curTake()), { rel: e.key === "ArrowRight" ? 5 : -5 }); }
  else if (e.key === "ArrowRight" || e.key === "ArrowLeft") { S.sel = (S.sel + (e.key === "ArrowRight" ? 1 : -1) + n) % n; render(); if (S.playing?.startsWith("t:")) play(tkey(curTake())); }
  else if (e.key.toLowerCase() === "a") ab();
  else if (e.key === "Enter") guard(() => act("pick"));
});
/* ---------------- right-click menu ----------------
   The app window has no browser menu, so text fields get their own: Cut, Copy, Paste, Select all.
   Paste reads the Windows clipboard through the app (the browser clipboard API may be blocked). */
let ctxTarget = null;
function closeCtx() { $("#ctx")?.remove(); }
document.addEventListener("contextmenu", (e) => {
  if (e.target.closest(".pv")) return;
  const f = e.target.closest("input:not([type=checkbox]):not([type=range]):not([type=file]),textarea");
  const sel = String(window.getSelection() || "");
  if (!f && !sel) { e.preventDefault(); closeCtx(); return; }
  e.preventDefault(); closeCtx(); ctxTarget = f;
  const hasSel = f ? f.selectionStart !== f.selectionEnd : !!sel, editable = f && !f.readOnly && !f.disabled;
  const m = document.createElement("div"); m.id = "ctx"; m.className = "ctx"; m.setAttribute("role", "menu");
  m.innerHTML = [["cut", "Cut", "Ctrl+X", editable && hasSel], ["copy", "Copy", "Ctrl+C", hasSel], ["paste", "Paste", "Ctrl+V", editable], ["all", "Select all", "Ctrl+A", !!f]]
    .map(([k, l, sc, on]) => `<button role="menuitem" data-ctx="${k}" ${on ? "" : "disabled"}><span>${l}</span><span class="mute small">${sc}</span></button>`).join("");
  document.body.appendChild(m);
  const r = m.getBoundingClientRect();
  m.style.left = Math.min(e.clientX, innerWidth - r.width - 8) + "px"; m.style.top = Math.min(e.clientY, innerHeight - r.height - 8) + "px";
});
document.addEventListener("mousedown", (e) => { if (!e.target.closest("#ctx")) closeCtx(); }, true);
window.addEventListener("blur", closeCtx);
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-ctx]"); if (!b) return;
  e.stopPropagation(); const k = b.dataset.ctx, f = ctxTarget; closeCtx();
  guard(async () => {
    const selText = f ? f.value.slice(f.selectionStart, f.selectionEnd) : String(window.getSelection() || "");
    if (k === "copy" || k === "cut") {
      const ok = await api("clipboard_set", { text: selText }).catch(() => false);
      if (!ok) await navigator.clipboard?.writeText(selText);
      if (k === "cut") { f.focus(); f.setRangeText("", f.selectionStart, f.selectionEnd, "end"); f.dispatchEvent(new Event("input", { bubbles: true })); f.dispatchEvent(new Event("change", { bubbles: true })); }
    } else if (k === "paste") {
      let txt = await api("clipboard_get").catch(() => null);
      if (txt == null) txt = await navigator.clipboard?.readText().catch(() => null);
      if (txt == null) throw new Error("Couldn't read the clipboard. Use Ctrl+V instead.");
      if (f.tagName === "INPUT") txt = txt.replace(/\s*\n+\s*/g, " ");
      f.focus(); f.setRangeText(txt, f.selectionStart, f.selectionEnd, "end");
      f.dispatchEvent(new Event("input", { bubbles: true })); f.dispatchEvent(new Event("change", { bubbles: true }));
    } else if (k === "all") { f.focus(); f.select(); }
  });
}, true);

boot().catch((e) => { document.body.innerHTML = `<pre style="color:#f88;padding:2rem">${esc(e.message)}</pre>`; });
