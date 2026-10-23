# Changelog

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
