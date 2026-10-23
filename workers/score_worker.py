"""Whisper + speaker check. Runs inside env-score.
  transcribe <wav> <out.txt>       draft the reference transcript (operator corrects it)
  score <job_dir> <voice_dir>      per take: words = 1 - WER vs the script, voice = ECAPA cosine vs reference
Scores are hints shown beside each take, never the decision. Accent is not scored: the public
accent classifier has no Taiwanese-English class and failed validation in the bake-off."""
import json, os, re, sys
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
from scipy.signal import resample_poly

DEV = "cuda" if torch.cuda.is_available() else "cpu"


def load16(path):
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if sr != 16000:
        g = np.gcd(sr, 16000); x = resample_poly(x, 16000 // g, sr // g).astype("float32")
    return x


def words(s):
    return re.sub(r"[^a-z0-9' ]+", " ", s.lower().replace("-", " ")).split()


def wer(ref, hyp):
    r, h = words(ref), words(hyp)
    if not r:
        return float("nan")
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]; d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1])); prev = cur
    return d[len(h)] / len(r)


def asr():
    from transformers import pipeline
    p = pipeline("automatic-speech-recognition", model="openai/whisper-large-v3-turbo", dtype=torch.float16, device=DEV)
    return lambda x: p({"raw": x, "sampling_rate": 16000}, return_timestamps=True,
                       generate_kwargs={"language": "en", "task": "transcribe"})["text"].strip()


def spk_model():
    from speechbrain.inference.classifiers import EncoderClassifier
    save = Path(os.environ.get("OA_ENGINES", ".")) / "sb" / "spkrec-ecapa-voxceleb"
    kw = dict(source="speechbrain/spkrec-ecapa-voxceleb", savedir=str(save), run_opts={"device": DEV})
    try:
        from speechbrain.utils.fetching import LocalStrategy
        return EncoderClassifier.from_hparams(**kw, local_strategy=LocalStrategy.COPY)
    except (ImportError, TypeError):
        return EncoderClassifier.from_hparams(**kw)


@torch.no_grad()
def emb(m, x):
    return m.encode_batch(torch.from_numpy(x)[None].to(DEV)).squeeze().cpu().numpy().astype("float64")


def write_json(p, obj):
    tmp = p.with_name(p.name + ".tmp"); tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8"); os.replace(tmp, p)


def main():
    mode = sys.argv[1]
    if mode == "transcribe":
        text = asr()(load16(sys.argv[2]))
        out = Path(sys.argv[3]); tmp = out.with_name(out.name + ".tmp")
        tmp.write_text(text, encoding="utf-8"); os.replace(tmp, out)
        return
    job, vdir = Path(sys.argv[2]), Path(sys.argv[3])
    spec = json.loads((job / "job.json").read_text(encoding="utf-8"))
    sp = job / "scores.json"
    scores = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    todo = [t for t in spec["takes"] if t["id"] not in scores and (job / "takes" / f"{t['id']}.wav").exists()]
    if not todo:
        return
    run_asr, m = asr(), spk_model()
    ref = emb(m, load16(vdir / "ref.wav"))
    for t in todo:
        x = load16(job / "takes" / f"{t['id']}.wav")
        hyp = run_asr(x)
        e = emb(m, x)
        scores[t["id"]] = {"words": round(max(0.0, 1 - wer(spec["parts"][t["part"]]["text"], hyp)), 3),
                           "voice": round(float(e @ ref / (np.linalg.norm(e) * np.linalg.norm(ref) + 1e-12)), 3),
                           "heard": hyp}
        write_json(sp, scores)


if __name__ == "__main__":
    main()
