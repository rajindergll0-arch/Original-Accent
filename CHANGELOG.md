# Changelog

## 0.4.0 — DaVinci Resolve bridge (beta)

**New**
- **Voice from Resolve:** use the clip selected in the Media Pool (its In and Out marks, if set) or the clip under the playhead (the part used in the edit). The cleanest section is picked inside that range.
- **Script from markers:** each note on the current timeline's markers becomes a part, in timeline order, filtered by marker colour. Parts remember their marker's position.
- **Send to Resolve:** import the picks into an *Original Accent* bin, and optionally place them on new audio tracks, at the playhead or back at their markers. Existing tracks are never touched.
- **Two ways to connect,** chosen in Settings: *Resolve Studio: direct* (Original Accent drives Resolve itself) or *through Resolve's Scripts menu* (for the free edition, where outside control was removed in Resolve 21.1).

**Known limits**
- Not yet tried against a real copy of Resolve: built against Resolve's documented scripting API, and tested with simulated Resolve on both routes. Please report anything that misbehaves.
- The Scripts-menu route assumes the free edition still runs Lua scripts from Workspace → Scripts.

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
