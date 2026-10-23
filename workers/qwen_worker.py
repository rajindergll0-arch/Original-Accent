"""Qwen3-TTS 1.7B-Base, full-reference (ICL) mode: reference audio + its transcript.
The mode that carries a speaker's accent. Runs inside env-qwen.
usage: qwen_worker.py <job_dir> <voice_dir>"""
import json, os, sys, time, traceback
from pathlib import Path
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"


def log_err(job, tid, msg):
    with open(job / "errors.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"take": tid, "engine": "qwen", "error": msg}) + "\n")


def main():
    job, vdir = Path(sys.argv[1]), Path(sys.argv[2])
    spec = json.loads((job / "job.json").read_text(encoding="utf-8"))
    voice = json.loads((vdir / "voice.json").read_text(encoding="utf-8"))
    todo = [t for t in spec["takes"] if t["engine"] == "qwen" and not (job / "takes" / f"{t['id']}.wav").exists()]
    if not todo:
        return
    model = Qwen3TTSModel.from_pretrained(MODEL, device_map="cuda:0", dtype=torch.bfloat16, attn_implementation="sdpa")
    prompt = model.create_voice_clone_prompt(ref_audio=str(vdir / "ref.wav"), ref_text=voice["transcript"],
                                             x_vector_only_mode=False)
    for t in todo:
        out = job / "takes" / f"{t['id']}.wav"
        tmp = out.with_name(out.stem + ".part.wav")
        torch.manual_seed(t["seed"])
        try:
            wavs, sr = model.generate_voice_clone(text=spec["parts"][t["part"]]["text"], language="English",
                                                  voice_clone_prompt=prompt, max_new_tokens=2048)
            w = wavs[0]
            if hasattr(w, "detach"):
                w = w.detach().float().cpu().numpy()
            sf.write(str(tmp), w.squeeze(), sr)
            os.replace(tmp, out)          # never hand over a half-written file
        except Exception:
            log_err(job, t["id"], traceback.format_exc()[-1500:])
    torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
