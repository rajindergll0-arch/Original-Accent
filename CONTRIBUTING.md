# Contributing

Thanks for helping. Original Accent is a small project, so a few notes keep things easy.

## Reporting problems
Open an issue with:
- what you did, what you expected, and what happened;
- your Windows version, GPU model and video memory;
- the error panel's **Copy details** text, or the relevant log from `%LOCALAPPDATA%\OriginalAccent\logs`.

Please don't attach recordings of real people's voices to issues.

## Working on the code
- **Layout:**
  - `original_accent/`: the app (local HTTP API, jobs, engine installs).
  - `workers/`: scripts that run inside each engine's own Python environment.
  - `ui/`: plain HTML, CSS and JS, with no build step.
  - `installer/`: the NSIS script.
- **Run without a GPU:** `OA_DEMO=1 python -m original_accent --browser` simulates the engines, so the whole UI can be worked on anywhere.
- **Read first:** [`docs/HANDOFF.md`](docs/HANDOFF.md) has the design decisions and the install lessons learned the hard way, such as how PyTorch versions are pinned per engine. Please read it before changing `engines.py`.
- **Keep the principles:**
  - Nothing runs in the cloud.
  - The operator decides; scores are hints only.
  - Engines stay isolated from each other.
  - Text and layout hold up at every window size, interface size and skin.

## Releases
Push a tag like `v0.3.1`. GitHub Actions builds the installer and attaches it to a draft release. Write the notes, then publish.
