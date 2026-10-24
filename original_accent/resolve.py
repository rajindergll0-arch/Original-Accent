"""DaVinci Resolve bridge.

Two routes to the same three things (a voice from a clip, a script from timeline markers,
picked takes into the edit):

- Studio: Original Accent drives Resolve directly through its scripting API
  (workers/resolve_worker.py, run as its own process). One click, nothing to do in Resolve.
- Free: from Resolve 21.1, outside programs can't control the free edition. Instead, small Lua
  scripts installed into Resolve's Workspace > Scripts menu do the Resolve side, and the two
  apps swap files in %LOCALAPPDATA%\\OriginalAccent\\resolve: the scripts write inbox-*.json
  (markers, a clip) for the app; the app writes outbox.lua (what to import and where) for the
  "Bring in takes" script. A Lua table file needs no JSON parser on the Resolve side.
"""
import json, os, subprocess, sys, time
from pathlib import Path
import soundfile as sf
from . import jobs, paths
from .paths import DATA, APP, WORKERS, NO_WINDOW, write_json, read_json

BRIDGE = DATA / "resolve"
LUA_SRC = APP / "resolve"
MENU = {"markers": "Original Accent - Send markers", "selected": "Original Accent - Send selected clip",
        "playhead": "Original Accent - Send clip at playhead", "takes": "Original Accent - Bring in takes"}


def resolve_dir():
    return Path(os.environ.get("OA_RESOLVE_DIR") or r"C:\Program Files\Blackmagic Design\DaVinci Resolve")


def installed():
    return paths.DEMO or (os.name == "nt" and (resolve_dir() / "Resolve.exe").exists())


def scripts_dir():
    base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    if paths.DEMO:
        base = DATA / "demo-appdata"
    return base / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Scripts" / "Utility"


# ------------------------------------------------------------------ Studio: direct

def call(op, **a):
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        exe = exe.with_name("python.exe")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if paths.DEMO:
        env["OA_DEMO"] = "1"
    try:
        p = subprocess.run([str(exe), str(WORKERS / "resolve_worker.py")], input=json.dumps({"op": op, **a}),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                           cwd=str(WORKERS), creationflags=NO_WINDOW, timeout=180)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Resolve didn't answer within 3 minutes. Is it showing a dialog?")
    line = (p.stdout.strip().splitlines() or [""])[-1]
    try:
        out = json.loads(line)
    except ValueError:
        raise RuntimeError("Talking to Resolve failed: " + (p.stderr.strip().splitlines() or ["no output"])[-1])
    if not out.get("ok"):
        raise RuntimeError(out.get("error") or "Resolve reported a problem.")
    return out


# ------------------------------------------------------------------ Free: menu scripts + files

def install_scripts():
    """Copy the Lua menu scripts into Resolve's per-user Scripts folder. Safe to repeat."""
    d = scripts_dir(); d.mkdir(parents=True, exist_ok=True)
    common = (LUA_SRC / "oa_common.lua").read_text(encoding="utf-8")
    for key, name in MENU.items():
        body = (LUA_SRC / f"{key}.lua").read_text(encoding="utf-8")
        # one self-contained file per menu item: Resolve runs each script on its own
        (d / f"{name}.lua").write_text(common + "\n" + body, encoding="utf-8")
    BRIDGE.mkdir(parents=True, exist_ok=True)
    return {"folder": str(d), "scripts": list(MENU.values())}


def console_lines(key):
    """The Console starts in Lua ("Lua>" prompt); it can be switched to Python. A line for each."""
    return {"lua": f"dofile([[{scripts_dir() / (MENU[key] + '.lua')}]])", "py": console_line(key)}


def console_line(key):
    """One line for Resolve's Console (Py3), doing what the menu item does. Resolve 21.1 free keeps
    console scripting (with Python built in) while the Workspace > Scripts menu needs Studio."""
    kind = {"markers": "markers", "selected": "selected", "playhead": "playhead", "takes": "takes"}[key]
    return (f'import importlib,sys;sys.path.insert(0,r"{WORKERS}");import resolve_console as c;'
            f'importlib.reload(c);c.run(globals(),"{kind}")')


def scripts_installed():
    return all((scripts_dir() / f"{n}.lua").exists() for n in MENU.values())


def _lua(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "nil"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "") + '"'
    if isinstance(v, (list, tuple)):
        return "{" + ", ".join(_lua(x) for x in v) + "}"
    return "{" + ", ".join(f"[{_lua(str(k))}] = {_lua(x)}" for k, x in v.items()) + "}"


def lua_table(text):
    """Parse a Lua table constructor, as Fusion's bmd.writefile saves one:
    { key = value, ["any key"] = value, [1] = value, value, ... } with strings, numbers,
    true/false/nil and nested tables. A table whose keys are 1..n becomes a list."""
    i, n = text.index("{"), len(text)

    def ws():
        nonlocal i
        while i < n:
            if text[i].isspace():
                i += 1
            elif text.startswith("--", i):
                j = text.find("\n", i); i = n if j < 0 else j + 1
            else:
                break

    def string():
        nonlocal i
        q = text[i]; i += 1; out = []
        while text[i] != q:
            c = text[i]
            if c == "\\":
                i += 1; c = text[i]
                if c.isdigit():
                    j = i
                    while j < n and j - i < 3 and text[j].isdigit():
                        j += 1
                    out.append(chr(int(text[i:j]))); i = j; continue
                out.append({"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v", "\n": "\n"}.get(c, c))
            else:
                out.append(c)
            i += 1
        i += 1
        return "".join(out)

    def value():
        nonlocal i
        ws()
        c = text[i]
        if c == "{":
            return table()
        if c in "\"'":
            return string()
        if c == "[" and text[i + 1] in "[=":
            j = text.index("]]", i); v = text[i + 2:j]; i = j + 2; return v
        j = i
        while j < n and (text[j].isalnum() or text[j] in "+-._"):
            j += 1
        tok = text[i:j]; i = j
        if tok == "true": return True
        if tok == "false": return False
        if tok == "nil": return None
        f = float(tok)
        return int(f) if f.is_integer() and "." not in tok and "e" not in tok.lower() else f

    def table():
        nonlocal i
        i += 1; d, pos = {}, 1
        while True:
            ws()
            if text[i] == "}":
                i += 1; break
            if text[i] == "[" and text[i + 1] not in "[=":
                i += 1; k = value(); ws(); i += 1; ws(); i += 1          # [key] =
                d[k] = value()
            else:
                j = i
                while j < n and (text[j].isalnum() or text[j] == "_"):
                    j += 1
                k = text[i:j]; m = j
                while m < n and text[m].isspace():
                    m += 1
                if k and m < n and text[m] == "=" and text[m + 1:m + 2] != "=":
                    i = m + 1; d[k] = value()
                else:
                    d[pos] = value(); pos += 1
            ws()
            if i < n and text[i] in ",;":
                i += 1
        if d and all(isinstance(k, int) for k in d) and sorted(d) == list(range(1, len(d) + 1)):
            return [d[k] for k in range(1, len(d) + 1)]
        return [] if not d else d

    return table()


def read_msg(path):
    """A message a Resolve script saved: JSON (Lua with io, or the Python Console route) or a
    Lua table (bmd.writefile, where Resolve's Console has no io). None if unreadable yet."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        v = lua_table(text)
        return v if isinstance(v, dict) else None
    except Exception:
        return None


def write_outbox(req):
    BRIDGE.mkdir(parents=True, exist_ok=True)
    (BRIDGE / "outbox.json").write_text(json.dumps(req), encoding="utf-8")   # for the Console route
    tmp = BRIDGE / "outbox.lua.part"
    tmp.write_text("return " + _lua(req) + "\n", encoding="utf-8")
    os.replace(tmp, BRIDGE / "outbox.lua")


def take_inbox(kind, since):
    """The newest message of this kind a menu script wrote after `since` (epoch seconds)."""
    BRIDGE.mkdir(parents=True, exist_ok=True)
    best = None
    for f in BRIDGE.glob(f"inbox-{kind}*.json"):
        if f.stat().st_mtime >= since - 1 and (best is None or f.stat().st_mtime > best.stat().st_mtime):
            best = f
    if not best:
        return None
    msg = read_msg(best)
    if msg is None:
        return None                       # still being written: try again on the next poll
    best.unlink(missing_ok=True)
    if not msg.get("ok", True):
        raise RuntimeError(msg.get("error") or "The Resolve script reported a problem.")
    return msg


def last_run(since):
    """Whether a menu script has run since `since`, and its last log lines: lets the page say
    "Resolve hasn't run it yet" or show what went wrong, instead of waiting silently."""
    logs = [f for f in (BRIDGE / "script-log.txt", BRIDGE / "script-last.txt") if f.exists()]
    if not logs:
        return {"ran": False, "tail": []}
    f = max(logs, key=lambda x: x.stat().st_mtime)
    if f.name == "script-last.txt":           # saved without io: one line, as a Lua table
        lines = [(read_msg(f) or {}).get("line", "")]
    else:
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()[-4:]
    return {"ran": f.stat().st_mtime >= since - 1, "tail": lines}


def outbox_result(since):
    f = BRIDGE / "outbox-result.json"
    if f.exists() and f.stat().st_mtime >= since - 1:
        msg = read_msg(f)
        if msg is None:
            return None
        f.unlink(missing_ok=True)
        for o in ("outbox.lua", "outbox.json"):      # handled: never import the same takes twice
            (BRIDGE / o).unlink(missing_ok=True)
        if msg and not msg.get("ok", True):
            raise RuntimeError(msg.get("error") or "Bringing in the takes failed in Resolve.")
        return msg
    return None


# ------------------------------------------------------------------ what both routes share

def tc(frame, fps, df=False):
    sys.path.insert(0, str(WORKERS))
    from resolve_worker import frames_to_tc
    return frames_to_tc(int(frame), fps, df)


def markers_result(m):
    """Normalise a markers message (from either route) for the Script page."""
    fps = float(m.get("fps") or 24)
    out = []
    for k in m.get("markers") or []:
        frame = int(k["frame"])
        out.append({"frame": frame, "tc": k.get("tc") or tc(frame, fps, bool(m.get("df"))),
                    "color": k.get("color", ""), "name": k.get("name", ""), "note": k.get("note", "")})
    return {"timeline": m.get("timeline"), "fps": fps, "markers": out}


def voice_from_clip(src, consent):
    """Add a voice from a clip Resolve pointed at: copy the file in (Resolve keeps the original),
    then start from the cleanest section inside the range the editor marked or used."""
    p = Path(src["path"])
    if not p.exists():
        raise RuntimeError(f"Original Accent can't open {p}. Is the drive connected?")
    if p.stat().st_size > jobs.MAX_UPLOAD:
        raise RuntimeError("That clip's file is over 4 GB. Set In and Out marks around the speaker in Resolve "
                           "and render just that part, or export its audio, then add it.")
    v = jobs.add_voice(src.get("name") or p.stem, p.name, p, consent, copy=True, span=src.get("range"))
    v["from_resolve"] = src.get("how")
    write_json(paths.VOICES / v["id"] / "voice.json", v)
    return v


def plan_send(jid, place):
    """What to import and where. place: none | playhead | markers."""
    j = jobs.job(jid)
    picks = {int(k): v for k, v in j["picks"].items()}
    if not picks:
        raise RuntimeError("Pick a take for at least one part first.")
    many, every = len(j["parts"]) > 1, all(i in picks for i in range(len(j["parts"])))
    joined = many and every and place in ("none", "playhead")
    if place == "playhead" and many and not every:
        missing = [p["label"] for i, p in enumerate(j["parts"]) if i not in picks]
        raise RuntimeError("Placing at the playhead uses the joined file, so every part needs a pick. Still to pick: "
                           + ", ".join(missing[:5]) + ("…" if len(missing) > 5 else ""))
    ex = jobs.export(jid, separate=(place != "playhead" or not many), joined=joined)
    files, spots = list(ex["files"]), []
    secs = lambda f: sf.info(f).frames / sf.info(f).samplerate
    if place == "playhead":
        f = ex["joined"] if many else ex["parts"][min(picks)]
        spots.append({"file": f, "at": "playhead", "offset": 0, "seconds": secs(f)})
        files = [f]
    elif place == "markers":
        at = {i: p["at"] for i, p in enumerate(j["parts"]) if p.get("at")}
        if not at:
            raise RuntimeError("This job wasn't made from Resolve markers, so there's nowhere to place its parts. "
                               "Use “At the playhead” or “Import only”.")
        for i, f in ex["parts"].items():
            if i in at:
                spots.append({"file": f, "frame": int(at[i]["frame"]), "seconds": secs(f)})
        files = [s["file"] for s in spots]
    return {"bin": ["Original Accent", j["name"][:60] or "Untitled"], "files": files, "place": spots,
            "track": "Original Accent", "job": j["name"]}


def send(jid, place, route):
    req = plan_send(jid, place)
    if route == "studio":
        r = call("send", **{k: req[k] for k in ("bin", "files", "place", "track", "job")})
        return {"done": True, **r}
    req["id"] = f"{int(time.time())}"
    write_outbox(req)
    return {"done": False, "menu": MENU["takes"], "console": console_lines("takes"), "files": len(req["files"]), "placed": len(req["place"])}
