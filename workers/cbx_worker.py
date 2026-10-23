"""Chatterbox, three settings. Runs inside env-cbx (Python 3.11).
  default  exaggeration 0.5, cfg_weight 0.5
  low      cfg_weight 0.05 — guidance almost off. Exactly 0 crashes chatterbox-tts 0.1.7
           (batch-size mismatch in T3 inference), so 0.05.
  turbo    Chatterbox-Turbo defaults
usage: cbx_worker.py <job_dir> <voice_dir>"""
import json, os, sys, traceback
from pathlib import Path
import soundfile as sf
import torch

KW = {"default": {"exaggeration": 0.5, "cfg_weight": 0.5}, "low": {"exaggeration": 0.5, "cfg_weight": 0.05}, "turbo": {}}


def log_err(job, tid, msg):
    with open(job / "errors.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"take": tid, "engine": "cbx", "error": msg}) + "\n")


def run(job, vdir, spec, todo, model):
    for t in todo:
        out = job / "takes" / f"{t['id']}.wav"
        tmp = out.with_name(out.stem + ".part.wav")
        torch.manual_seed(t["seed"])
        try:
            wav = model.generate(spec["parts"][t["part"]]["text"], audio_prompt_path=str(vdir / "ref.wav"), **KW[t["config"]])
            sf.write(str(tmp), wav.squeeze(0).detach().cpu().numpy(), model.sr)
            os.replace(tmp, out)
        except Exception:
            log_err(job, t["id"], traceback.format_exc()[-1500:])


def main():
    job, vdir = Path(sys.argv[1]), Path(sys.argv[2])
    spec = json.loads((job / "job.json").read_text(encoding="utf-8"))
    todo = [t for t in spec["takes"] if t["engine"] == "cbx" and not (job / "takes" / f"{t['id']}.wav").exists()]
    std = [t for t in todo if t["config"] in ("default", "low")]
    tur = [t for t in todo if t["config"] == "turbo"]
    if std:
        try:
            from chatterbox.tts import ChatterboxTTS
            m = ChatterboxTTS.from_pretrained(device="cuda"); run(job, vdir, spec, std, m)
            del m; torch.cuda.empty_cache()
        except Exception:
            for t in std:
                log_err(job, t["id"], traceback.format_exc()[-1500:])
    if tur:
        try:
            from chatterbox.tts_turbo import ChatterboxTurboTTS
            m = ChatterboxTurboTTS.from_pretrained(device="cuda"); run(job, vdir, spec, tur, m)
        except Exception:
            for t in tur:
                log_err(job, t["id"], traceback.format_exc()[-1500:])


if __name__ == "__main__":
    main()
