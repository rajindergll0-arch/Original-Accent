"""Where everything lives. One data root per user; nothing is written next to the app."""
import json, os, sys, time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent          # repo / install root
UI = APP / "ui"
WORKERS = APP / "workers"

if os.name == "nt":
    _base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
else:
    _base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
DATA = Path(os.environ.get("OA_DATA", _base / "OriginalAccent"))
OLD_DATA = _base / "Voicecast"          # the app's working title before release


def _migrate():
    """Move voices, jobs, engines and settings from the pre-release "Voicecast" folder, once,
    so nothing has to be re-downloaded. The installer does this too; this covers source runs."""
    if "OA_DATA" in os.environ or not OLD_DATA.is_dir():
        return
    import shutil
    DATA.mkdir(parents=True, exist_ok=True)
    for name in ("engines", "voices", "jobs", "logs", "settings.json"):
        src, dst = OLD_DATA / name, DATA / name
        if src.exists() and not dst.exists():
            try:
                shutil.move(str(src), str(dst))
            except Exception:
                pass


_migrate()
ENGINES = DATA / "engines"        # isolated Python environments + model caches
VOICES = DATA / "voices"
JOBS = DATA / "jobs"
LOGS = DATA / "logs"
EXPORTS = Path(os.environ.get("OA_EXPORTS", Path.home() / "Music" / "Original Accent"))
SETTINGS = DATA / "settings.json"

DEMO = os.environ.get("OA_DEMO") == "1"   # simulated engines: UI work without a GPU

for d in (DATA, ENGINES, VOICES, JOBS, LOGS):
    d.mkdir(parents=True, exist_ok=True)

NO_WINDOW = 0x08000000 if os.name == "nt" else 0   # no console windows stealing focus


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def write_json(path, obj):
    """Atomic: written beside, then renamed, so a reader never sees half a file."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    for _ in range(20):                       # Windows: a reader may hold the file a moment
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05)
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


DEFAULT_SETTINGS = {"skin": "grade", "ui_scale": 1.0, "takes_per_part": 5,
                    "include_chatterbox": True, "chatterbox_configs": ["default", "low", "turbo"],
                    "export_dir": str(EXPORTS), "free_gpu_before_run": True,
                    "check_updates": True}


SETTINGS_VERSION = 2   # v2: five Qwen takes per part by default


def settings():
    s = dict(DEFAULT_SETTINGS)
    saved = read_json(SETTINGS, {}) or {}
    if saved.get("v", 1) < 2 and saved.get("takes_per_part") == 3:
        saved["takes_per_part"] = 5          # the old default, not a choice the operator made
    s.update(saved)
    return s


def save_settings(patch):
    s = settings()
    s.update({k: v for k, v in patch.items() if k in DEFAULT_SETTINGS})
    write_json(SETTINGS, s | {"v": SETTINGS_VERSION})
    return s


def py_exe():
    return Path(sys.executable)
