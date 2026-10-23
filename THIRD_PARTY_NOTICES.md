# Third-party notices

Original Accent is a desktop front end. The voice cloning itself is done by open-source models and
libraries made by other people, and the app would not exist without them. This file lists them,
what each one does here, and its licence.

The licences below were checked on 2026-10-23 against each project's own page. Licences can
change, so check the linked pages before you rely on them, especially for commercial use of
generated audio.

## Voice engines and models
These are downloaded by the app on first run. They are not part of this repository or the installer.

| Project | Made by | Used for | Licence |
|---|---|---|---|
| [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) (`Qwen3-TTS-12Hz-1.7B-Base` weights, `qwen-tts` package) | Qwen team, Alibaba Cloud | The main voice engine: clones a voice from a clip and its transcript | Apache-2.0 ([model card](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base)) |
| [Chatterbox](https://github.com/resemble-ai/chatterbox) (`chatterbox-tts`, Chatterbox and Chatterbox-Turbo weights) | Resemble AI | The optional second voice engine | MIT ([model card](https://huggingface.co/ResembleAI/chatterbox)) |
| [Whisper large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo) | OpenAI | Drafting transcripts; checking each take's words | MIT |
| [SpeechBrain ECAPA speaker verification](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb) | SpeechBrain | Checking how alike each take sounds to the reference | Apache-2.0 |

**Audio watermark.** Every file Chatterbox generates carries Resemble AI's
Perth watermark ([described in the Chatterbox README](https://github.com/resemble-ai/chatterbox)): inaudible, and built to survive MP3
compression and editing. Original Accent does not add or remove watermarks. Qwen3-TTS takes are
not watermarked by the model.

## Software libraries
Installed from PyPI by the installer or on first run.

| Project | Used for | Licence |
|---|---|---|
| [PyTorch](https://pytorch.org) / torchaudio | Running the models on the GPU | BSD-3-Clause |
| [Hugging Face Transformers](https://github.com/huggingface/transformers), [huggingface_hub](https://github.com/huggingface/huggingface_hub) | Loading Whisper; downloading model files | Apache-2.0 |
| [SpeechBrain](https://github.com/speechbrain/speechbrain) | Speaker check | Apache-2.0 |
| [pywebview](https://github.com/r0x0r/pywebview) | The app window (uses Microsoft Edge WebView2) | BSD-3-Clause |
| [NumPy](https://numpy.org), [SciPy](https://scipy.org) | Audio maths | BSD-3-Clause |
| [python-soundfile](https://github.com/bastibe/python-soundfile) / libsndfile | Reading and writing WAV | BSD-3-Clause / LGPL-2.1 |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | Supplies the ffmpeg program | BSD-2-Clause |
| [FFmpeg](https://ffmpeg.org) | Reading audio from audio and video files, cutting sections. The build that imageio-ffmpeg supplies on Windows (7.1) is configured with `--enable-gpl --enable-version3`, so it is GPL-3.0. Original Accent runs it as a separate program and does not distribute it. | GPL-3.0 (that build) |

## Bundled in the installer

| Project | Used for | Licence | Text |
|---|---|---|---|
| [uv](https://github.com/astral-sh/uv) 0.9.5, Astral Software | Creating the app's and engines' Python environments | MIT or Apache-2.0 | `licenses/uv-LICENSE-MIT.txt`, `licenses/uv-LICENSE-APACHE.txt` |
| [NSIS](https://nsis.sourceforge.io) | The Windows installer itself | zlib/libpng | |

## Fonts
Bundled in `ui/fonts`, all under the SIL Open Font License 1.1. The full texts are in `licenses/`.

| Font | Used by skin | Licence text |
|---|---|---|
| [Inter](https://rsms.me/inter/) | Grade, Reel | `licenses/font-inter-OFL.txt` |
| [JetBrains Mono](https://www.jetbrains.com/lp/mono/) | Grade | `licenses/font-jetbrains-mono-OFL.txt` |
| [Martian Mono](https://github.com/evilmartians/mono) | Reel | `licenses/font-martian-mono-OFL.txt` |
| [IBM Plex Mono](https://github.com/IBM/plex) | Signal | `licenses/font-ibm-plex-mono-OFL.txt` |
| [Space Grotesk](https://github.com/floriankarsten/space-grotesk) | Signal | `licenses/font-space-grotesk-OFL.txt` |
| [Archivo](https://github.com/Omnibus-Type/Archivo) | Booth | `licenses/font-archivo-OFL.txt` |

The font files were taken from the [Fontsource](https://fontsource.org) packages.
