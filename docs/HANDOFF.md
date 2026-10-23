# Original Accent: hand-off notes

For whoever picks this up next, whether another model (e.g. Claude Fable) or a person. Read this first, then `README.md`.


## v0.3.0 (2026-10-23): first public release
- **Renamed:** the app was called Voicecast while it was being built. It's now **Original Accent**: package `original_accent`, data folder `%LOCALAPPDATA%\OriginalAccent`, environment variables `OA_*`. The installer and `paths._migrate()` move voices, jobs, engines and settings from the old `Voicecast` folder, so nothing re-downloads, and remove the old copy and its shortcuts.
- **Consent:** adding a recording requires ticking "I have the speaker's permission to clone their voice". The server refuses uploads without it, and the confirmation is stored in `voice.json`.
- **Watermark disclosure:** Chatterbox's Perth watermark is stated on the setup screen, beside the Script switch, in the README and in `THIRD_PARTY_NOTICES.md`.
- **Repo:** MIT licence (Rajinder Gill), `THIRD_PARTY_NOTICES.md` with licences checked on 2026-10-23, font OFL and uv licence texts in `licenses/`, CI (syntax, demo-mode UI test, installer build), and a tagged-release workflow that builds the installer on GitHub and drafts the release.

## Status (v0.1.0, 2026-10-23)
- **Built by Claude Opus 5.5.** The whole UI flow (voice, script, generate, compare, pick, deliver, settings, first-run setup) passes end to end in **demo mode**, across all four skins, at 1366×768 and 2560×1440 at 150% device scale. Neither size scrolls sideways and there are no console errors.
- **Not yet run on a real GPU in this form.** The engine workers and the installer are carried over from scripts that did run on the RTX 4090 (the October 2026 bake-off and the narration runs). This packaging is new, though. The first real run will surface Windows-specific issues; fix them there.

## v0.2.4 (2026-10-23)
- **Scroll position:** switching pages starts the new page at the top. Re-drawing the same page (progress updates, playback) keeps the scroll position.

## v0.2.3 (2026-10-23): long recordings
- **Limits, stated on the Voice page:** up to 4 GB per file and 3 hours of audio. Anything larger is refused with a plain message saying what to do.
- **Nothing large is held in memory:**
  - Uploads stream to disk in 1 MB pieces, with progress shown.
  - Waveform overviews and the section finder read audio in blocks.
  - The server answers Range requests by seeking, so scrubbing a long file doesn't re-read it.
  - ffmpeg's conversion timeout is 30 min.
  - Video sources over 200 MB are dropped once their audio is extracted.
- **Measured:** a 1-hour WAV converted, had its section suggested and was ready in 5.3 s, with the app process at 45 MB.
- **Copy:** the Voice page now says Original Accent *picks* the cleanest 6–15 s and the operator can move it. Choosing a section was never required.

## v0.2.2 (2026-10-23): long-script copy review
- **One set of numbers everywhere:** about 90 words (around 40 s) suits both engines, and Qwen alone manages about 350 words (around 2½ min). The intro, the per-part warnings and the guide used to disagree (100 vs 90).
- **The lengths are said once:** the Script intro no longer repeats them three times or tells people to split by hand. It points to the guide, and the guide says plainly that Auto-split does the splitting and how chunks are labelled.
- **The seed advice is softened** to what we actually know: "may help… trust your ear". It hasn't been measured.
- **Durations over 90 s read as "about 3 min 26 s".**

## v0.2.1 (2026-10-23)
- **Line breaks:** hyphenated compounds and number ranges ("multi-agent", "6–15") no longer split across lines (word joiners around the hyphen or dash). Words of three letters or fewer travel with the next word, so none is left at a line end, including after ; : , or .
- **One reading measure** in rem (44rem) for lead and note text alike, so paragraphs of different sizes line up.
- **Text areas grow with their content** (up to 60% of the window height, then scroll) and no longer have resize handles.

## v0.2.0 (2026-10-23): typography and scaling
- **Text system:**
  - A type scale (`--fs-*`), and one reading measure (68ch) for every explanatory paragraph.
  - Ragged-right alignment with `text-wrap: pretty`; headings use `balance`.
  - Normal word breaking (`break-word`, not `anywhere`, which let flex items shrink and break mid-word). Paths and transcripts still wrap anywhere.
  - Tabular figures for times, scores and counts.
- **Typesetting pass** (`typeset()` after each render): non-breaking spaces keep numbers with their units, keep short parentheticals and quotes on one line (the Script page's "(for example “G X ten”)"), and stop short words (a, the, to…) dangling at line ends. Inputs and text areas are never touched.
- **Scaling model:**
  - Windows display scaling is handled by the window.
  - The base text size steps by window size class (14/15/16/17 px), never continuously, multiplied by the Interface size setting and a per-skin trim (Signal ×0.94 for its wider monospace face).
  - Layouts reflow by their own width in rem (container queries), so a large interface size on a small window reflows like a narrow window.
  - The top bar and page bar shrink and truncate instead of overflowing.
- **Checked:** a matrix of 1100×720 / 1366×768 / 1920×1080 / 2560×1440 × interface size 80/100/125/160% × 4 skins × 6 pages, with no text outside its box and no sideways scrolling.

## v0.1.9 (2026-10-23)
- **Long scripts:**
  - *Auto-split* on the Script page (per part, or for all long parts) breaks text at paragraph ends first, then sentence ends, then clause marks. Chunks are about 80 words with Chatterbox on and about 150 with it off.
  - Chunks keep a `group` and a `brk` (`para`/`sentence`). *Merge chunks* undoes a split.
  - Deliver gains *Play all picks*, which plays the picks in order with the same pauses the export uses.
  - A joined export (`jobs.export(joined=True)`) trims each take's edges, matches speech level to −20 dBFS RMS with a −1 dBFS ceiling, and inserts pauses of 0.35 s mid-paragraph, 0.8 s at paragraph ends and 1.0 s between separate parts, writing `<job>_complete.wav`.
- **Guidance in the app:** an "About long scripts" panel (opens by itself when long or split parts are present) appears on Script and Deliver. It covers what stays consistent between chunks (voice, timbre, accent), what can vary (pace, energy, pitch, loudness, chunk edges), and how to keep the joins seamless. Compare shows a tip about picking the same take number across parts, which share a seed.

## v0.1.8 (2026-10-23)
- **Right-click menu:** every text field has its own Cut / Copy / Paste / Select all menu, because the WebView2 window shows no browser menu. Paste and copy go through the Windows clipboard on the Python side (`clipboard_get` / `clipboard_set`), falling back to `navigator.clipboard`.
- **Length guide:** each part shows its word count and an estimated duration at about 140 words per minute. It warns when Chatterbox would cut off (over about 90 words, roughly 40 s; about 1000 speech tokens at 25 Hz) and when Qwen would (over about 350 words, roughly 170 s; 2048 tokens of its 12 Hz codec). There's no automatic splitting yet.

## v0.1.7 (2026-10-23)
- **Stuck installs:** every setup command now streams its output live into the log and the UI (`engines.run_live`), with hard timeouts: 15 min for resolving, 60 min for package installs. Before each install, uv processes left over from an interrupted install are ended. They hold uv's cache lock and were the likely cause of "Finding the right PyTorch build" never finishing.
- **Install progress sits on the engine's own row** in Settings and in first-run setup: "Step n of 6", the step name, a bar, the last line the installer printed, and time on this step. Other engines show as queued.
- **Installer:** before copying, it closes every process running from `%LOCALAPPDATA%\Original Accent`, and it never stops on a locked `uv.exe`.

## v0.1.5 (2026-10-23)
- **Chatterbox install bug fixed:** uv was called as `pythonw -m uv`, and under pythonw its output was lost. The resolver's "which torch" answer came back empty, so the newest torch was installed, and `chatterbox-tts` (which pins torch 2.6.0) then failed against the constraints, with no error text. uv is now always called directly (the bundled `bin/uv.exe`, else `uv.find_uv_bin()`). The resolver answer is logged, and installing never falls back to guessing a torch version. Verified that the dry-run gives `+ torch==2.6.0` for Chatterbox on Python 3.11.
- **Wording:** the installer and setup now say "It can soften an accent, so you can choose whether it is used for each run."

## v0.1.4 (2026-10-23)
- **Text overflow fixed everywhere:** long names are truncated with the full text on hover, and paths and transcripts wrap. Checked with a test that flags any text extending past its box, across every page and skin at 1366×768.
- **Every skin lists every take:** takes still rendering show as greyed placeholders, so the count never jumps. The default is now 5 Qwen takes per part, and old saved settings that still hold the previous default of 3 are moved to 5.
- **Scores sit on each take:** labelled "Word accuracy" and "Voice match" as percentages, with an explanation on hover. Grade's separate Scopes column was removed.
- **Updates:** Settings → Updates checks each engine's packages (`uv pip list --outdated`) and model revisions (Hugging Face API, compared with the local `refs/main`), automatically at most once a day, fetching metadata only. "Update" reinstalls that engine with `--upgrade`. Checking for new app versions waits for a GitHub release feed.

## v0.1.3 (2026-10-23)
- **Real installer:** `installer/original-accent.nsi` builds `dist/OriginalAccent-Setup-<v>.exe`. It installs per user and bundles `uv.exe`, so no Python is needed beforehand. A components page explains each engine, and the operator's choices are written to `install-choices.json`. The app installs those engines on first launch. The uninstaller asks whether to keep user data.
- **Whisper + speaker check is now optional** ("recommended"). Without it, transcripts are typed by hand and runs skip scoring.
- **Scrubbing everywhere:** any waveform is a scrub bar (click, drag, or scroll to step through). One transport (start, −5 s, play, +5 s, time readout) appears on every playback. The server answers HTTP Range requests so seeking works.
- **Section picker:** the Voice page shows the whole upload (`full.wav`) with draggable handles. *Suggest cleanest section* runs `jobs.suggest_trim`: 20 ms energy voice activity, cut only at pauses of at least 0.18 s, windows of 6–15 s scored for continuous speech, noise floor and clipping, preferring about 11 s. Uploads over 15 s are auto-trimmed to the suggestion.
- **Errors:** errors now open a draggable panel that can be closed, with a one-line summary, "Show details", "Copy details" and "Open log folder". Info toasts sit top-centre with a close button.
- **Engine installs** end with a "ready" dialog offering an optional restart. None is needed, because engines run as subprocesses.
- **Taskbar identity:** a new icon, with its own taskbar identity (AppUserModelID) and window icon set through Win32.

## Principles (decided with the operator, don't drift)
- **No cloud model at runtime.** Everything runs locally.
- **The operator starts it, steers it and decides.** The system does the work in between. Never present the app as autonomous.
- **Qwen3-TTS full-reference is the core engine.** Chatterbox is optional; the operator chooses whether it is used for each run, and the switch explains why you would or wouldn't use it.
- **Scores are hints.** Whisper word match and ECAPA voice match are hints only. Accent is judged by ear (the public CommonAccent model has no Taiwanese-English class and failed validation).
- **The UI must not look like a typical Claude-made app.** No cream backgrounds, serif display type, soft orange or rounded-card grids. Each skin follows its own reference world.
- **Engine colours are fixed across skins:** Qwen cyan `#4CC9E8`, Chatterbox amber `#F2A541`, words violet `#A97FE0`, voice green `#4FD08A`.

## Architecture
```
Install from source.cmd -> installer/install.ps1   uv + app env (Py 3.12) + shortcuts
original_accent/main.py      single instance, per-monitor DPI awareness, sizes window from the screen, pywebview (WebView2)
original_accent/server.py    127.0.0.1 HTTP API + static UI, per-launch token on every call and media URL
original_accent/jobs.py      voices, jobs, runner thread (stages in order, resumable), export, setup thread
original_accent/engines.py   isolated engine envs (uv), CUDA-torch pinning, GPU info, frees Ollama VRAM, ffmpeg
workers/*.py           run inside each engine env as windowless subprocesses
ui/                    index.html + app.css (4 skins as token sets) + app.js (no build step), bundled OFL fonts
```
Data lives in `%LOCALAPPDATA%\Original Accent`: `engines/` (environments, Hugging Face cache), `voices/<id>/` (source file, `ref.wav` at 24 kHz mono, `voice.json`), `jobs/<id>/` (`job.json`, `takes/*.wav`, `scores.json`, `errors.jsonl`), `logs/`, `settings.json`.

## Install lessons (paid for once; do not rediscover)
- Install torch and torchaudio from the PyTorch CUDA index, pinned to the exact versions the packages want. Then install everything else against a per-environment constraints file. A shared constraints file polluted installs, and an unpinned resolver pulled a CPU-only torch.
- Chatterbox needs Python 3.11 and `setuptools<81` (its watermarker imports `pkg_resources`).
- Chatterbox `cfg_weight=0` crashes (chatterbox-tts 0.1.7, batch-size mismatch), so "low" uses 0.05.
- Write every output to a `.part` file and rename it when complete. A half-written WAV was once handed over.
- Run workers windowless (`CREATE_NO_WINDOW`, `pythonw`). Console windows stole keyboard focus.
- Ollama can hold about 20 GB of VRAM. Free it before GPU stages (a setting, on by default).
- Shared network folders served stale cached files. The app keeps its working data local.

## Scaling
- The process is per-monitor DPI aware (v2) before any window exists, and WebView2 renders at native DPI.
- The root font size is `clamp()`'d to the window width and multiplied by the operator's interface-size setting (80–160%). Every size in the UI is in `rem`.
- Layouts reflow below 1000 and 1250 px. Waveforms are canvases redrawn at `devicePixelRatio`, both on resize and on DPI change.
- The window opens at 85% of the screen's work area, clamped to between 1100×720 and 1920×1200.

## Next steps
1. First real run on the 4090. Fix whatever the install or workers hit, and log it here.
2. A visual trim on the Voice page (drag handles on the waveform) in place of the number fields.
3. A proper Windows installer (`.exe` via Inno Setup or similar) and code signing, then a GitHub release.
4. Optionally, Qwen's embedding-only mode as an advanced setting (it flattens accent, so leave it off by default).
5. An app name decision. "Original Accent" is a working title.
