"""Voices, jobs and the runner. The runner does what the bake-off's worker did: stages in
order, each resumable, finished takes skipped, nothing half-written ever handed over."""
import math, os, re, shutil, subprocess, threading, time, uuid
from pathlib import Path
import numpy as np
import soundfile as sf
from . import engines, paths
from .paths import VOICES, JOBS, WORKERS, LOGS, NO_WINDOW, now, write_json, read_json

CBX_CONFIGS = {"default": "Default", "low": "Low guidance", "turbo": "Turbo"}
LOCK = threading.Lock()
RUN = {"state": "idle", "kind": None, "job": None, "stage": "", "done": 0, "total": 0, "message": "", "error": None,
       "error_detail": None, "error_log": None, "finished": []}


def _set(**kw):
    with LOCK:
        RUN.update(kw, updated=now())


def fail(e):
    """Operator-facing summary on its own line; the technical tail kept for 'Show details'."""
    msg = str(e).strip()
    _set(state="error", error=getattr(e, "summary", None) or (msg.splitlines()[0][:300] if msg else "Something went wrong."),
         error_detail=getattr(e, "detail", None) or msg[-1800:], error_log=getattr(e, "log", None))


def run_state():
    with LOCK:
        return dict(RUN)


def busy():
    return run_state()["state"] == "running"


def slug(s, n=40):
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
    return (s or "untitled")[:n]


def new_id(prefix):
    return f"{prefix}{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


# ---------------------------------------------------------------- audio helpers

MAX_UPLOAD = 4 * 1024 ** 3      # 4 GB: a long video file is fine; only its sound is kept
MAX_SECONDS = 3 * 3600          # 3 hours of audio per recording


def peaks(path, n=400):
    """Waveform overview, read in blocks so a long recording never has to fit in memory."""
    try:
        info = sf.info(str(path))
    except Exception:
        return {"peaks": [], "duration": 0}
    total = info.frames
    if total == 0:
        return {"peaks": [], "duration": 0}
    step = max(1, total // n)
    out = []
    for blk in sf.blocks(str(path), blocksize=step, dtype="float32", always_2d=True):
        out.append(float(np.abs(blk).max()) if len(blk) else 0.0)
        if len(out) >= n:
            break
    top = max(out) or 1.0
    return {"peaks": [round(v / top, 3) for v in out], "duration": round(total / info.samplerate, 2)}


def frame_levels(path, frame_s=0.02):
    """Per-frame level (dB) and clipping flags, streamed in blocks."""
    info = sf.info(str(path)); sr = info.samplerate; hop = max(1, int(sr * frame_s))
    db, clip = [], []
    for blk in sf.blocks(str(path), blocksize=hop * 1000, dtype="float32", always_2d=True):
        x = blk.mean(axis=1); m = len(x) // hop
        if m == 0:
            continue
        fr = x[: m * hop].reshape(m, hop)
        db.append(20 * np.log10(np.sqrt((fr ** 2).mean(axis=1) + 1e-12) + 1e-9))
        clip.append((np.abs(fr) > 0.985).any(axis=1))
    if not db:
        return np.zeros(0), np.zeros(0, bool), sr, info.frames / sr
    return np.concatenate(db), np.concatenate(clip), sr, info.frames / sr


def convert(src, dst, start=None, end=None):
    tmp = Path(dst).with_name(Path(dst).stem + ".part.wav")
    argv = [engines.ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
    if start:
        argv += ["-ss", str(start)]
    argv += ["-i", str(src)]
    if end:
        argv += ["-t", str(float(end) - float(start or 0))]
    argv += ["-ac", "1", "-ar", "24000", str(tmp)]
    subprocess.run(argv, check=True, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, timeout=1800,
                   capture_output=True)
    os.replace(tmp, dst)


def _cut(src, dst, s, e):
    x, sr = sf.read(str(src), dtype="float32")
    tmp = Path(dst).with_name(Path(dst).stem + ".part.wav")
    sf.write(str(tmp), x[int(s * sr):int(e * sr)], sr); os.replace(tmp, dst)


def _demo_wav(path, seed, secs=6.0):
    rng = np.random.default_rng(seed)
    sr = 24000; t = np.arange(int(sr * secs)) / sr
    env = np.abs(np.sin(t * (1.3 + rng.random()))) * (0.4 + 0.6 * np.abs(np.sin(t * 7.1 + seed)))
    y = (env * np.sin(2 * math.pi * (110 + 40 * rng.random()) * t) * 0.3).astype("float32")
    tmp = Path(path).with_name(Path(path).stem + ".part.wav")
    sf.write(str(tmp), y, sr); os.replace(tmp, path)


# ---------------------------------------------------------------- workers

def worker(args, log):
    """Run an engine worker in its own environment, windowless; raise with the log tail."""
    env_name = {"qwen_worker.py": "qwen", "cbx_worker.py": "cbx", "score_worker.py": "score"}[args[0]]
    lf = LOGS / f"{log}.log"
    with open(lf, "a", encoding="utf-8", errors="replace") as f:
        f.write(f"\n===== {now()} {' '.join(map(str, args))}\n"); f.flush()
        p = subprocess.run([str(engines.env_python(env_name)), str(WORKERS / args[0]), *map(str, args[1:])],
                           stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                           env=engines.child_env(), creationflags=NO_WINDOW)
    if p.returncode != 0:
        raise engines.StepError(f"The {env_name} engine stopped with an error.",
                                lf.read_text(encoding="utf-8", errors="replace")[-1800:], lf)


# ---------------------------------------------------------------- voices

def voices():
    out = []
    for d in sorted(VOICES.iterdir(), reverse=True):
        v = read_json(d / "voice.json")
        if v:
            out.append(v)
    return out


def voice(vid):
    return read_json(VOICES / vid / "voice.json")


def add_voice(name, filename, upload, consent=False, copy=False, span=None):
    """upload: a file already streamed to disk by the server (never held in memory).
    copy: leave `upload` where it is (a file the editor's project still uses).
    span: [start, end] seconds the cleanest section should come from (a Resolve clip's marks)."""
    if not consent:
        if not copy:
            Path(upload).unlink(missing_ok=True)
        raise RuntimeError("Confirm you have the speaker's permission before adding a recording.")
    vid = new_id("v")
    d = VOICES / vid; d.mkdir(parents=True)
    src = d / ("source" + (Path(filename).suffix.lower() or ".wav"))
    (shutil.copy2 if copy else shutil.move)(str(upload), src)
    try:
        if paths.DEMO:
            _demo_wav(d / "full.wav", 7, 24.0)
        else:
            try:
                convert(src, d / "full.wav")      # whole file, 24 kHz mono: what the trim view shows
            except subprocess.CalledProcessError as e:
                raise RuntimeError("Couldn't read any audio from that file. Is it an audio or video file?") from e
            except subprocess.TimeoutExpired as e:
                raise RuntimeError("That file took too long to convert. Trim it to the part with the speaker first.") from e
        full = sf.info(str(d / "full.wav")).frames / sf.info(str(d / "full.wav")).samplerate
        if full > MAX_SECONDS:
            raise RuntimeError(f"That recording is {full / 3600:.1f} hours long. Original Accent takes up to 3 hours; "
                               "trim it to the part with the speaker first.")
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise
    src_kept = src.stat().st_size <= 200 * 1024 ** 2
    if not src_kept:                           # a big video: the 24 kHz audio is all we need from it
        src.unlink(missing_ok=True)
    shutil.copy2(d / "full.wav", d / "ref.wav")
    full = round(full, 2)
    v = {"id": vid, "name": name or Path(filename).stem, "transcript": "", "created": now(),
         "trim": None, "full_duration": full, "duration": full, "auto_trimmed": False,
         "consent": {"confirmed": bool(consent), "at": now()}}
    write_json(d / "voice.json", v)
    if span:
        span = [max(0.0, float(span[0])), min(full, float(span[1]))]
        if span[1] - span[0] < 0.5:
            span = None
    if span and span[1] - span[0] <= 15:       # the editor's own range is short enough: use it as is
        v = update_voice(vid, {"trim": span}); v["auto_trimmed"] = True; write_json(d / "voice.json", v)
    elif full > 15 or span:                    # too long to clone from: start from the best section
        s, e = suggest_trim(vid, span=span)["trim"]
        v = update_voice(vid, {"trim": [s, e]})
        v["auto_trimmed"] = True
        write_json(d / "voice.json", v)
    return v


def ensure_full(vid):
    """Voices made before v0.1.3 have no full.wav; make it from the original upload."""
    d = VOICES / vid
    if not (d / "full.wav").exists():
        src = next(d.glob("source.*"), None)   # older voices only
        if src is None or paths.DEMO:
            shutil.copy2(d / "ref.wav", d / "full.wav")
        else:
            convert(src, d / "full.wav")
        v = voice(vid); v.setdefault("full_duration", peaks(d / "full.wav")["duration"]); write_json(d / "voice.json", v)
    return d / "full.wav"


def suggest_trim(vid, lo=6.0, hi=15.0, target=11.0, span=None):
    """Find the cleanest stretch to clone from: continuous speech, a quiet floor, no clipping,
    starting and ending in a pause so no word is cut, as close to ~11 s as the clip allows.
    Energy-based voice activity on 20 ms frames; every candidate window runs pause to pause."""
    db, clip, sr, total_s = frame_levels(ensure_full(vid))
    off = 0.0
    if span:                                   # only look inside this stretch (20 ms frames)
        a, b = int(span[0] * 50), int(span[1] * 50)
        db, clip, off = db[a:b], clip[a:b], a / 50
    n = len(db)
    if n < 10:
        return {"trim": [round(off, 2), round(off + n / 50 if span else total_s, 2)], "reason": "Clip is very short."}
    floor = np.percentile(db, 10); speech = db > max(floor + 12, db.max() - 45)
    k = 5; sm = np.convolve(speech.astype(float), np.ones(k) / k, mode="same") > 0.4   # bridge tiny gaps
    # pauses: runs of >= 0.18 s non-speech; their midpoints are allowed cut points
    cuts, run = [0], 0
    for i, sp in enumerate(sm):
        run = 0 if sp else run + 1
        if run == 9:
            cuts.append(i - 4)
    cuts.append(n)
    cuts = sorted(set(cuts))
    best, best_score = None, -1e9
    fps = 50.0
    for a in range(len(cuts)):
        for b in range(a + 1, len(cuts)):
            dur = (cuts[b] - cuts[a]) / fps
            if dur < lo:
                continue
            if dur > hi:
                break
            seg = slice(cuts[a], cuts[b])
            sp_ratio = sm[seg].mean()
            noise = np.percentile(db[seg], 10) - floor           # lower = quieter floor in this stretch
            long_gap = max((len(g) for g in "".join("1" if v else "0" for v in sm[seg]).split("1")), default=0) / fps
            score = 3 * sp_ratio - 0.08 * abs(dur - target) - 0.03 * max(noise, 0) - 4 * clip[seg].mean() - 0.6 * max(long_gap - 0.8, 0)
            if score > best_score:
                best_score, best = score, (cuts[a], cuts[b], sp_ratio)
    if best is None:   # no pause-to-pause window fits: take the speechiest ~11 s
        w = int(min(target, n / fps) * fps)
        sums = np.convolve(sm.astype(float), np.ones(w), mode="valid")
        i = int(sums.argmax()); best = (i, i + w, sums[i] / w)
    s, e = off + max(0.0, best[0] / fps - 0.05), off + min(n / fps, best[1] / fps + 0.05)
    return {"trim": [round(s, 2), round(e, 2)], "speech": round(float(best[2]), 2),
            "reason": f"{e - s:.1f} s, {int(best[2] * 100)}% speech, cut at pauses"}


def update_voice(vid, patch):
    d = VOICES / vid; v = voice(vid)
    if "trim" in patch and patch["trim"]:
        s, e = patch["trim"]
        full = ensure_full(vid)
        convert(full, d / "ref.wav", s, e) if not paths.DEMO else _cut(full, d / "ref.wav", s, e)
        v["trim"] = [s, e]; v["duration"] = peaks(d / "ref.wav")["duration"]; v["auto_trimmed"] = False
    for k in ("name", "transcript"):
        if k in patch:
            v[k] = patch[k]
    write_json(d / "voice.json", v)
    return v


def transcribe(vid):
    """Whisper drafts the reference transcript; the operator corrects it."""
    d = VOICES / vid
    if not engines.ready("score"):
        raise RuntimeError("Whisper isn't installed. Type the transcript, or add Whisper in Settings.")
    _set(state="running", kind="transcribe", job=None, stage="Transcribing reference", done=0, total=1, error=None)
    try:
        if paths.DEMO:
            time.sleep(1.2); text = "This is a demo transcript of the reference clip. Correct it to match exactly."
        else:
            engines.free_gpu()
            worker(["score_worker.py", "transcribe", d / "ref.wav", d / "transcript.txt"], "transcribe")
            text = (d / "transcript.txt").read_text(encoding="utf-8").strip()
        update_voice(vid, {"transcript": text})
        _set(state="done", done=1, message="Transcript drafted. Check it against the clip.")
    except Exception as e:
        fail(e)


# ---------------------------------------------------------------- jobs

def plan(job):
    takes = []
    for pi, _ in enumerate(job["parts"]):
        for k in range(job["takes_per_part"]):
            takes.append({"id": f"p{pi}-qwen-t{k + 1}", "part": pi, "engine": "qwen", "config": "full",
                          "seed": 1234 + k, "label": f"Take {k + 1}"})
        if job["include_chatterbox"]:
            for cfg in job["chatterbox_configs"]:
                takes.append({"id": f"p{pi}-cbx-{cfg}-1", "part": pi, "engine": "cbx", "config": cfg,
                              "seed": 1234, "label": CBX_CONFIGS.get(cfg, cfg)})
    return takes


def jobs():
    out = []
    for d in sorted(JOBS.iterdir(), reverse=True):
        j = read_json(d / "job.json")
        if j:
            out.append({k: j[k] for k in ("id", "name", "voice_id", "created")} | {"parts": len(j["parts"])})
    return out


def job(jid):
    d = JOBS / jid
    j = read_json(d / "job.json")
    if not j:
        return None
    scores = read_json(d / "scores.json", {}) or {}
    for t in j["takes"]:
        f = d / "takes" / f"{t['id']}.wav"
        t["ready"] = f.exists()
        t["scores"] = scores.get(t["id"])
    return j


def create_job(spec):
    s = paths.settings()
    jid = new_id("j")
    # group/brk come from auto-split: chunks of one piece share a group; brk says whether the
    # chunk ends a paragraph ("para") or mid-paragraph ("sentence"), which sets the pause when joined
    parts = [{"label": p.get("label") or f"Part {i + 1}", "text": p["text"],
              **({"group": p["group"]} if p.get("group") else {}), **({"brk": p["brk"]} if p.get("brk") else {}),
              **({"at": {k: p["at"][k] for k in ("frame", "tc") if p["at"].get(k) is not None}} if p.get("at") else {})}
             for i, p in enumerate(spec["parts"]) if p.get("text", "").strip()]
    if not parts:
        raise ValueError("The script is empty.")
    j = {"id": jid, "name": spec.get("name") or "Untitled", "voice_id": spec["voice_id"], "parts": parts,
         "takes_per_part": int(spec.get("takes_per_part", s["takes_per_part"])),
         "include_chatterbox": bool(spec.get("include_chatterbox", s["include_chatterbox"])) and engines.ready("cbx"),
         "chatterbox_configs": spec.get("chatterbox_configs", s["chatterbox_configs"]),
         "created": now(), "picks": {}, **({"resolve": spec["resolve"]} if spec.get("resolve") else {})}
    j["takes"] = plan(j)
    (JOBS / jid / "takes").mkdir(parents=True)
    write_json(JOBS / jid / "job.json", j)
    return j


def save_job(j):
    j = {k: v for k, v in j.items()}
    j["takes"] = [{k: v for k, v in t.items() if k not in ("ready", "scores")} for t in j["takes"]]
    write_json(JOBS / j["id"] / "job.json", j)


def more_takes(jid, part, n=2):
    j = job(jid)
    have = [t for t in j["takes"] if t["part"] == part and t["engine"] == "qwen"]
    start = len(have)
    for k in range(start, start + n):
        j["takes"].append({"id": f"p{part}-qwen-t{k + 1}", "part": part, "engine": "qwen", "config": "full",
                           "seed": 1234 + k, "label": f"Take {k + 1}"})
    if j["include_chatterbox"]:
        rnd = 1 + max([int(t["id"].rsplit("-", 1)[1]) for t in j["takes"] if t["part"] == part and t["engine"] == "cbx"] or [0])
        for cfg in j["chatterbox_configs"]:
            j["takes"].append({"id": f"p{part}-cbx-{cfg}-{rnd}", "part": part, "engine": "cbx", "config": cfg,
                               "seed": 1234 + rnd, "label": f"{CBX_CONFIGS.get(cfg, cfg)} · {rnd}"})
    save_job(j)
    return start_run(jid)


def pick(jid, part, take_id):
    j = job(jid); j["picks"][str(part)] = take_id; save_job(j)
    return j


def _count(jid):
    j = job(jid)
    return sum(t["ready"] for t in j["takes"]), len(j["takes"])


def _run(jid):
    d = JOBS / jid; j = job(jid); v = VOICES / j["voice_id"]
    try:
        if not (voice(j["voice_id"]) or {}).get("transcript"):
            raise RuntimeError("The voice has no transcript. Full-reference cloning needs it.")
        if paths.settings()["free_gpu_before_run"] and not paths.DEMO:
            _set(stage="Freeing GPU memory"); engines.free_gpu()
        stages = [("qwen", "Cloning · Qwen3-TTS")]
        if j["include_chatterbox"]:
            stages.append(("cbx", "Cloning · Chatterbox"))
        for eng, label in stages:
            _set(stage=label)
            if paths.DEMO:
                for t in job(jid)["takes"]:
                    f = d / "takes" / f"{t['id']}.wav"
                    if t["engine"] == eng and not f.exists():
                        time.sleep(0.6); _demo_wav(f, hash(t["id"]) % 1000)
                        _set(done=_count(jid)[0])
            else:
                stop = threading.Event()
                def tick():
                    while not stop.wait(2):
                        _set(done=_count(jid)[0])
                th = threading.Thread(target=tick, daemon=True); th.start()
                try:
                    worker([f"{eng}_worker.py", d, v], f"{eng}-{jid}")
                finally:
                    stop.set()
            _set(done=_count(jid)[0])
        _set(stage="Checking · Whisper + speaker check")
        if not engines.ready("score"):
            pass                                  # optional: no scores, takes are judged by ear only
        elif paths.DEMO:
            time.sleep(1)
            rng = np.random.default_rng(3)
            write_json(d / "scores.json", {t["id"]: {"words": round(0.88 + 0.1 * rng.random(), 3),
                                                     "voice": round(0.72 + 0.08 * rng.random(), 3)} for t in job(jid)["takes"]})
        else:
            worker(["score_worker.py", "score", d, v], f"score-{jid}")
        missing = [t["id"] for t in job(jid)["takes"] if not t["ready"]]
        _set(state="done", stage="Done", done=_count(jid)[0],
             message=(f"{len(missing)} take(s) failed; see the log." if missing else "All takes ready"))
    except Exception as e:
        fail(e)


def start_run(jid):
    if busy():
        raise RuntimeError("Something is already running.")
    done, total = _count(jid)
    _set(state="running", kind="job", job=jid, stage="Starting", done=done, total=total, error=None, message="", finished=[])
    threading.Thread(target=_run, args=(jid,), daemon=True).start()
    return run_state()


PAUSE = {"sentence": 0.35, "para": 0.8, "part": 1.0}   # seconds of silence at each kind of join
TARGET_DB, PEAK_DB = -20.0, -1.0                       # speech level and ceiling for the joined file


def _speech_level(x, sr):
    """RMS level of the speech only (20 ms frames above a noise gate), in dBFS."""
    hop = max(1, int(sr * 0.02)); n = len(x) // hop
    if n == 0:
        return -60.0
    fr = x[: n * hop].reshape(n, hop); db = 10 * np.log10((fr ** 2).mean(axis=1) + 1e-12)
    act = fr[db > max(db.max() - 35, -55)]
    return float(10 * np.log10((act ** 2).mean() + 1e-12)) if act.size else -60.0


def _trim(x, sr, keep=0.06):
    """Cut leading and trailing silence, keeping a few ms so words aren't clipped."""
    hop = max(1, int(sr * 0.01)); n = len(x) // hop
    if n == 0:
        return x
    db = 20 * np.log10(np.abs(x[: n * hop]).reshape(n, hop).max(axis=1) + 1e-9)
    on = np.where(db > max(db.max() - 40, -50))[0]
    if not len(on):
        return x
    a = max(0, on[0] * hop - int(keep * sr)); b = min(len(x), (on[-1] + 1) * hop + int(keep * sr))
    return x[a:b]


def _load24(path):
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if sr != 24000:
        tmp = Path(path).with_name(Path(path).stem + ".24k.wav")
        convert(path, tmp); x, sr = sf.read(str(tmp), dtype="float32"); tmp.unlink(missing_ok=True)
    return x, 24000


def export(jid, dest=None, separate=True, joined=False):
    """Separate files: each picked take as its own named WAV.
    Joined: every picked part in script order in one WAV. Each take is trimmed of edge silence,
    brought to the same speech level, and joined with a pause that suits the break: short inside
    a paragraph, longer at a paragraph end, longest between separate parts."""
    j = job(jid); dest = Path(dest or paths.settings()["export_dir"]) / slug(j["name"])
    dest.mkdir(parents=True, exist_ok=True)
    out, by_part, joined_file = [], {}, None
    picks = sorted(((int(k), v) for k, v in j["picks"].items()), key=lambda kv: kv[0])
    if separate:
        for part, tid in picks:
            t = next(x for x in j["takes"] if x["id"] == tid)
            name = f"{slug(j['name'])}_{slug(j['parts'][part]['label'], 60)}_{t['engine']}-{t['config']}_{slug(t['label'])}.wav"
            shutil.copy2(JOBS / jid / "takes" / f"{tid}.wav", dest / name)
            out.append(str(dest / name)); by_part[part] = str(dest / name)
    if joined:
        missing = [p["label"] for i, p in enumerate(j["parts"]) if str(i) not in j["picks"]]
        if missing:
            raise RuntimeError("Pick a take for every part before joining. Still to pick: " + ", ".join(missing[:5]) + ("…" if len(missing) > 5 else ""))
        pieces = []
        for idx, (part, tid) in enumerate(picks):
            x, sr = _load24(JOBS / jid / "takes" / f"{tid}.wav")
            x = _trim(x, sr)
            x = x * (10 ** ((TARGET_DB - _speech_level(x, sr)) / 20))
            pieces.append(x.astype("float32"))
            if idx < len(picks) - 1:
                p, nxt = j["parts"][part], j["parts"][picks[idx + 1][0]]
                same = p.get("group") and p.get("group") == nxt.get("group")
                gap = PAUSE[p.get("brk", "para")] if same else PAUSE["part"]
                pieces.append(np.zeros(int(gap * sr), dtype="float32"))
        y = np.concatenate(pieces)
        peak = np.abs(y).max() or 1.0
        lim = 10 ** (PEAK_DB / 20)
        if peak > lim:
            y = y * (lim / peak)
        name = f"{slug(j['name'])}_complete.wav"
        tmp = dest / (name + ".part.wav"); sf.write(str(tmp), y, sr); os.replace(tmp, dest / name)
        out.append(str(dest / name)); joined_file = str(dest / name)
    return {"folder": str(dest), "files": out, "parts": by_part, "joined": joined_file}


# ---------------------------------------------------------------- setup

def start_setup(names, upgrade=False):
    if busy():
        raise RuntimeError("Something is already running.")
    names = [n for n in names if n in engines.ENVS]
    _set(state="running", kind="setup", job=None, stage="Starting", done=0, total=len(names), error=None, message="", finished=[],
         queue=names, engine=names[0] if names else None, step_i=0, step_n=len(engines.STEPS), detail="", step_text="Starting",
         started=time.time(), step_started=time.time())

    def go():
        try:
            for i, n in enumerate(names):
                title = engines.ENVS[n]["title"]
                _set(engine=n, started=time.time(), step_i=0, step_n=len(engines.STEPS), detail="")
                def step(key, text, t=title):
                    _set(stage=f"{t} · {text}", step_text=text, step_i=engines.STEPS.index(key), step_started=time.time(), detail="")
                def detail(line):
                    _set(detail=line[:160])
                if paths.DEMO:
                    for k in engines.STEPS:
                        step(k, engines.STEP_TEXT[k])
                        for d in ("Resolved 125 packages in 3.1s", "Prepared 40 packages in 12.4s")[:1 if k != "pkgs" else 2]:
                            time.sleep(0.6); detail(d)
                else:
                    engines.make_env(n, step=step, upgrade=upgrade, detail=detail)
                _set(done=i + 1, finished=names[:i + 1], step_i=len(engines.STEPS))
            if upgrade:
                (paths.ENGINES / "updates.json").unlink(missing_ok=True)
            _set(state="done", stage="Ready", message="Engines updated" if upgrade else "Engines installed")
        except Exception as e:
            fail(e)
    threading.Thread(target=go, daemon=True).start()
    return run_state()
