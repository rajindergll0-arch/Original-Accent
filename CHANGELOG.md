# Changelog

## 0.4.0 — DaVinci Resolve bridge (beta)

**New**
- **Voice from Resolve:** use the clip selected in the Media Pool (its In and Out marks, if set) or the clip under the playhead (the part used in the edit). The cleanest section is picked inside that range.
- **Script from markers:** each note on the current timeline's markers becomes a part, in timeline order, filtered by marker colour. Parts remember their marker's position.
- **Send to Resolve:** import the picks into an *Original Accent* bin, and optionally place them on new audio tracks, at the playhead or back at their markers. Existing tracks are never touched.
- **Two ways to connect,** chosen in Settings: *Resolve Studio: direct* (Original Accent drives Resolve itself) or *Resolve (free)*, where outside control was removed in 21.1: markers come from Resolve's marker EDL export, voices from the clip's file, and takes go in by pasting one line into Resolve's Console.

**Setting it up**
- Install over 0.3.0: voices, jobs, engines and settings are kept.
- Open **Settings → DaVinci Resolve** and choose your edition. For Studio, also set Resolve's **Preferences → System → General → External scripting using** to **Local**.
- With the free edition, Original Accent adds a few items to Resolve's Workspace → Scripts menu. Resolve 21.1 free lists them but won't run them from there; paste the line the app shows into **Workspace → Console** instead. Uninstalling Original Accent removes these items.

**Known limits**
- Confirmed on Resolve 21.1.1 (free): takes into the edit through the Console. Not yet confirmed on real Resolve: the Studio route, and markers from an EDL. Both are tested against a simulated Resolve; please report anything that misbehaves.
- With the free edition, Resolve can't tell Original Accent when it has finished, so you press *It's done* after the Console says so.

## 0.3.0 — first public release (beta)

**What's in it**
- **Voice:** add audio or video up to 3 hours (with consent confirmed). The cleanest 6–15 s is picked automatically and can be moved with handles; Whisper drafts the transcript.
- **Script:** split into parts, with a word count and estimated duration per part, length warnings for each engine, and Auto-split for long scripts.
- **Engines:** Qwen3-TTS (5 takes per part by default), with optional Chatterbox (3 settings). Each engine runs in its own isolated environment and is installed on first run with step-by-step progress.
- **Compare:** every take scored for word accuracy and voice match, as hints. Scrub, A/B against the reference, and keyboard shortcuts.
- **Deliver:** named WAV per part, plus an optional single joined file with matched loudness and natural pauses. *Play all picks* lets you hear the joins first.
- **Look:** four skins (Grade, Reel, Signal, Booth), an interface-size setting, and per-monitor DPI support.
- **Updates:** a daily engine update check that fetches metadata only, with one-click engine updates.

**Known limits**
- Windows with an NVIDIA GPU only. Tested on one machine: Windows 11, RTX 4090.
- Chatterbox likely doesn't run on RTX 50-series cards: it needs PyTorch 2.6, which has no build for them.
- English only. Output is WAV, 24 kHz mono.
- The installer isn't code-signed yet, so SmartScreen will warn.
