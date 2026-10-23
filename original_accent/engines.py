"""Engine environments: one isolated Python per engine, so one breaking never takes the
others down. Install logic carried over from the 2026-10 bake-off, where each rule below
was paid for (see docs/HANDOFF.md, "Install lessons")."""
import json, os, re, shutil, subprocess, time, urllib.request
from pathlib import Path
from . import paths
from .paths import ENGINES, LOGS, NO_WINDOW, now, write_json, read_json

TORCH_IDX = "https://download.pytorch.org/whl/{}"
CUDA_TAGS = ["cu128", "cu126", "cu130", "cu124"]   # first index carrying the wanted torch wins

ENVS = {
    "qwen":  {"title": "Qwen3-TTS", "py": "3.12", "pkgs": ["qwen-tts", "soundfile", "numpy", "huggingface_hub"],
              "models": ["Qwen/Qwen3-TTS-12Hz-1.7B-Base"], "required": True},
    # setuptools<81: Chatterbox's watermarker imports pkg_resources, dropped by newer setuptools.
    "cbx":   {"title": "Chatterbox", "py": "3.11", "pkgs": ["chatterbox-tts", "soundfile", "setuptools<81", "huggingface_hub"],
              "models": [], "required": False},
    "score": {"title": "Whisper + speaker check", "py": "3.12",
              "pkgs": ["transformers", "speechbrain", "soundfile", "scipy", "numpy", "torchaudio", "huggingface_hub"],
              "models": ["openai/whisper-large-v3-turbo", "speechbrain/spkrec-ecapa-voxceleb"], "required": False},
}
OLLAMA = "http://localhost:11434"


class StepError(RuntimeError):
    """A failure with a one-line summary for the operator and the log tail kept separately."""
    def __init__(self, summary, detail="", log=None):
        super().__init__(summary)
        self.summary, self.detail, self.log = summary, detail, str(log) if log else None


def uv_cmd():
    """The uv binary itself, never "pythonw -m uv": under pythonw the wrapper's output is lost,
    so the resolver's answer (which torch to install) came back empty and a mismatched torch
    went in (2026-10-23, Chatterbox install failing with no message)."""
    for c in (paths.APP / "bin" / ("uv.exe" if os.name == "nt" else "uv"),):
        if c.exists():
            return [str(c)]
    try:
        from uv import find_uv_bin
        return [find_uv_bin()]
    except Exception:
        pass
    w = shutil.which("uv")
    return [w] if w else [str(paths.py_exe().with_name("python.exe" if os.name == "nt" else "python")), "-m", "uv"]


def env_dir(name):
    return ENGINES / f"env-{name}"


def env_python(name):
    d = env_dir(name)
    return d / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def marker(name):
    return ENGINES / f"{name}.ok.json"


def child_env():
    e = dict(os.environ)
    e.update(HF_HOME=str(ENGINES / "hf"), HF_HUB_DISABLE_SYMLINKS_WARNING="1",
             PYTHONIOENCODING="utf-8", PYTHONUTF8="1", TORCH_HOME=str(ENGINES / "torch"),
             OA_ENGINES=str(ENGINES))
    return e


def _log(log, text):
    with open(LOGS / f"{log}.log", "a", encoding="utf-8", errors="replace") as f:
        f.write(text)


def capture(argv, timeout=None):
    p = subprocess.run([str(a) for a in argv], capture_output=True, text=True, errors="replace",
                       stdin=subprocess.DEVNULL, env=child_env(), cwd=str(ENGINES),
                       creationflags=NO_WINDOW, timeout=timeout)
    return p.returncode, p.stdout + p.stderr


def sh(argv, log, timeout=None):
    lf = LOGS / f"{log}.log"
    with open(lf, "a", encoding="utf-8", errors="replace") as f:
        f.write(f"\n===== {now()}  {' '.join(map(str, argv))}\n")
        f.flush()
        p = subprocess.run([str(a) for a in argv], stdout=f, stderr=subprocess.STDOUT,
                           stdin=subprocess.DEVNULL, env=child_env(), cwd=str(ENGINES),
                           creationflags=NO_WINDOW, timeout=timeout)
    if p.returncode != 0:
        tail = lf.read_text(encoding="utf-8", errors="replace")[-2000:]
        raise StepError(f"A setup step failed ({Path(str(argv[0])).name} exited {p.returncode}).", tail, lf)


def status():
    out = {}
    for n, spec in ENVS.items():
        m = read_json(marker(n))
        out[n] = {"title": spec["title"], "required": spec["required"],
                  "installed": bool(m) or paths.DEMO, "info": m or ({"demo": True} if paths.DEMO else None)}
    return out


def ready(name):
    return paths.DEMO or marker(name).exists()


def run_live(argv, log, on_line=lambda line: None, timeout=None):
    """Run a command, streaming every line into the log and to on_line as it arrives (so the
    UI can show what is happening), with a hard timeout so a stuck step can never hang setup."""
    import threading
    lf = LOGS / f"{log}.log"
    out = []
    with open(lf, "a", encoding="utf-8", errors="replace") as f:
        f.write(f"\n===== {now()}  {' '.join(map(str, argv))}\n"); f.flush()
        p = subprocess.Popen([str(a) for a in argv], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, env=child_env(), cwd=str(ENGINES), creationflags=NO_WINDOW,
                             text=True, encoding="utf-8", errors="replace", bufsize=1)

        def pump():
            for line in p.stdout:
                out.append(line); f.write(line); f.flush()
                if line.strip():
                    on_line(line.strip())
        t = threading.Thread(target=pump, daemon=True); t.start()
        try:
            rc = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill(); t.join(5)
            raise StepError(f"A setup step took longer than {int(timeout // 60)} minutes and was stopped.",
                            "".join(out)[-1800:], lf)
        t.join(5)
    return rc, "".join(out)


def kill_stale_uv():
    """Only one install runs at a time, so any uv still running from Original Accent's own copy is
    left over from an earlier, interrupted install. It holds uv's cache lock, which makes the
    next install wait forever ("Finding the right PyTorch build" that never finishes)."""
    if os.name != "nt":
        return
    root = str(paths.DATA)
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Get-Process uv -ErrorAction SilentlyContinue | Where-Object {{ $_.Path -like '{root}\\*' }} | Stop-Process -Force"],
                   creationflags=NO_WINDOW, capture_output=True, timeout=30)


STEP_TEXT = {"resolve": "Finding the right PyTorch build", "venv": "Creating environment", "torch": "Installing PyTorch with CUDA",
             "pkgs": "Installing the engine", "gpu": "Checking the GPU", "models": "Downloading model files"}
STEPS = ["venv", "resolve", "torch", "pkgs", "gpu", "models"]


def make_env(name, step=lambda key, text: None, upgrade=False, detail=lambda line: None):
    """1) ask the resolver which torch the packages want, install exactly that from the first
    CUDA index that has it; 2) install the rest with torch/torchaudio frozen by a per-env
    constraints file (a shared one polluted installs); 3) refuse a CPU-only torch."""
    spec, py, uv = ENVS[name], env_python(name), uv_cmd()
    log = f"env-{name}"
    kill_stale_uv()
    step("venv", STEP_TEXT["venv"])
    if not py.exists():
        rc, out = run_live([*uv, "venv", env_dir(name), "-p", spec["py"]], log, detail, timeout=900)
        if rc != 0:
            raise StepError(f"Couldn't create the {spec['title']} environment.", out[-1800:], LOGS / f"{log}.log")
    step("resolve", STEP_TEXT["resolve"])
    rc, out = run_live([*uv, "pip", "install", "--dry-run", "-p", py,
                        "--reinstall-package", "torch", "--reinstall-package", "torchaudio",
                        "torch", "torchaudio", *spec["pkgs"]], log, detail, timeout=900)
    m = re.search(r"\+ torch==([0-9][0-9.]*)", out); want = m.group(1) if m else None
    m = re.search(r"\+ torchaudio==([0-9][0-9.]*)", out); want_ta = m.group(1) if m else None
    if not want:
        # Never guess: installing the newest torch instead makes the engine's own install fail
        # against the pin (Chatterbox requires an exact torch).
        raise StepError(f"Couldn't work out which PyTorch {spec['title']} needs.", out[-1800:], LOGS / f"{log}.log")
    ta = f"torchaudio=={want_ta}" if want_ta else "torchaudio"
    step("torch", f"Installing PyTorch {want} with CUDA")
    for tag in CUDA_TAGS:
        detail(f"Trying the {tag} build")
        rc, out = run_live([*uv, "pip", "install", "-p", py, "--index-url", TORCH_IDX.format(tag),
                            "--reinstall-package", "torch", "--reinstall-package", "torchaudio",
                            f"torch=={want}", ta], log, detail, timeout=3600)
        if rc == 0:
            break
    else:
        raise StepError(f"No CUDA build of PyTorch {want} could be installed for {spec['title']}.", out[-1800:], LOGS / f"{log}.log")
    rc, ver = capture([py, "-c", "from importlib.metadata import version as v;"
                       "print('torch=='+v('torch')); print('torchaudio=='+v('torchaudio'))"])
    pins = re.findall(r"(?m)^torch(?:audio)?==\S+$", ver)
    if rc != 0 or len(pins) != 2:
        raise StepError("Could not read the installed PyTorch versions.", ver[-1500:], LOGS / f"{log}.log")
    cons = ENGINES / f"constraints-{name}.txt"
    cons.write_text("\n".join(pins) + "\n", encoding="utf-8")
    step("pkgs", f"Installing {spec['title']}")
    rc, out = run_live([*uv, "pip", "install", "-p", py, "-c", cons, *(["--upgrade"] if upgrade else []), *spec["pkgs"]],
                       log, detail, timeout=3600)
    if rc != 0:
        raise StepError(f"Installing {spec['title']}'s packages failed.", out[-1800:], LOGS / f"{log}.log")
    step("gpu", STEP_TEXT["gpu"])
    rc, out = capture([py, "-c", "import torch,sys; print(torch.__version__, torch.version.cuda, "
                       "torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none');"
                       "sys.exit(0 if torch.cuda.is_available() else 3)"])
    _log(log, out)
    if rc != 0:
        raise StepError("PyTorch installed but cannot see the NVIDIA GPU.", out[-1500:], LOGS / f"{log}.log")
    step("models", STEP_TEXT["models"])
    for model in spec["models"]:
        detail(f"Downloading {model.split('/')[-1]}")
        # Only the weights the engine loads: Whisper repos also carry Flax/TF/ONNX copies of the
        # same model, which would double the download for nothing.
        ign = ["*.msgpack", "*.h5", "*.ot", "*onnx*", "*.tflite", "flax_*", "tf_*"]
        sh([py, "-c", "from huggingface_hub import snapshot_download; "
                      f"snapshot_download({model!r}, ignore_patterns={ign!r})"], log)
    write_json(marker(name), {"at": now(), "torch": out.strip().splitlines()[-1] if out.strip() else ""})


def gpu_info():
    if paths.DEMO:
        return {"ok": True, "name": "Demo GPU", "total_gb": 24.0, "used_gb": 6.1}
    exe = shutil.which("nvidia-smi")
    if not exe:
        return {"ok": False, "name": None, "error": "No NVIDIA driver found (nvidia-smi missing)."}
    try:
        rc, out = capture([exe, "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"], timeout=10)
        name, tot, used = [s.strip() for s in out.strip().splitlines()[0].split(",")]
        return {"ok": True, "name": name, "total_gb": round(float(tot) / 1024, 1), "used_gb": round(float(used) / 1024, 1)}
    except Exception as e:
        return {"ok": False, "name": None, "error": str(e)}


def ollama_models():
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/ps", timeout=3) as r:
            return [m["name"] for m in json.load(r).get("models", [])]
    except Exception:
        return []


def free_gpu():
    """Unload models other local apps (ollama) hold in VRAM. Silent if nothing is running."""
    models = ollama_models()
    for m in models:
        req = urllib.request.Request(f"{OLLAMA}/api/generate", data=json.dumps({"model": m, "keep_alive": 0}).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=60).read()
        except Exception:
            pass
    if models:
        time.sleep(3)
    return models


def ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg") or "ffmpeg"


# ---------------------------------------------------------------- updates
# Only metadata is fetched (PyPI via uv, the Hugging Face model API); no audio or text leaves the PC.
MAIN_PKG = {"qwen": "qwen-tts", "cbx": "chatterbox-tts", "score": "transformers"}
PINNED = {"torch", "torchaudio"}   # follow the engine's own requirement on update, never bumped alone


def _local_rev(repo):
    ref = ENGINES / "hf" / "hub" / ("models--" + repo.replace("/", "--")) / "refs" / "main"
    try:
        return ref.read_text().strip()
    except Exception:
        return None


def _remote_rev(repo):
    try:
        with urllib.request.urlopen(f"https://huggingface.co/api/models/{repo}", timeout=15) as r:
            return json.load(r).get("sha")
    except Exception:
        return None


def _pkg_name(req):
    return re.split(r"[<>=!~;\[ ]", req, maxsplit=1)[0].strip().lower().replace("_", "-")


def _pending_upgrades(n):
    """What Update would actually change, asked of the resolver with the same constraints Update
    uses. A plain 'outdated' list also names versions the engine can't take (Chatterbox caps
    setuptools below 81), which then show as available forever however often Update runs."""
    spec, py = ENVS[n], env_python(n)
    cons = ENGINES / f"constraints-{n}.txt"
    argv = [*uv_cmd(), "pip", "install", "--dry-run", "--upgrade", "-p", py,
            *(["-c", cons] if cons.exists() else []), *spec["pkgs"]]
    rc, txt = capture(argv, timeout=300)
    if rc != 0:
        raise RuntimeError(txt.strip().splitlines()[-1] if txt.strip() else f"uv exited {rc}")
    old = {_pkg_name(a): b for a, b in re.findall(r"(?m)^\s*-\s+(\S+?)==(\S+)", txt)}
    new = {_pkg_name(a): b for a, b in re.findall(r"(?m)^\s*\+\s+(\S+?)==(\S+)", txt)}
    wanted = {_pkg_name(p) for p in spec["pkgs"]}
    return [{"name": k, "version": old[k], "latest": v} for k, v in sorted(new.items())
            if k in wanted and k not in PINNED and k in old and old[k] != v]


def check_updates():
    out = {"checked": now(), "engines": {}}
    for n, spec in ENVS.items():
        if not ready(n):
            continue
        if paths.DEMO:
            pk = [{"name": MAIN_PKG[n], "version": "0.1.0", "latest": "0.1.1"}] if n != "score" else []
            out["engines"][n] = {"title": spec["title"], "packages": pk, "models": [], "error": None}
            continue
        e = {"title": spec["title"], "packages": [], "models": [], "error": None}
        try:
            e["packages"] = _pending_upgrades(n)
        except Exception as ex:
            e["error"] = f"Couldn't check packages: {ex}"
        for repo in spec["models"]:
            lo, re_ = _local_rev(repo), _remote_rev(repo)
            if lo and re_ and lo != re_:
                e["models"].append({"name": repo, "local": lo[:8], "latest": re_[:8]})
        out["engines"][n] = e
    out["any"] = any(v["packages"] or v["models"] for v in out["engines"].values())
    write_json(ENGINES / "updates.json", out)
    return out


def last_updates():
    return read_json(ENGINES / "updates.json")
