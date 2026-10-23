"""Local-only HTTP API. Bound to 127.0.0.1 with a per-launch token, so other pages on the
machine cannot drive it. The UI is plain files; the same API works in the app window and in
a browser (handy for development: OA_DEMO=1 python -m original_accent --browser)."""
import json, mimetypes, os, secrets, subprocess, sys, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from . import engines, jobs, paths
from .paths import UI, VOICES, JOBS

TOKEN = secrets.token_urlsafe(16)
WINDOW = {"w": None}          # set by main.py when a native window exists


def choose_folder():
    w = WINDOW["w"]
    if w is None:
        return None
    import webview
    r = w.create_file_dialog(webview.FOLDER_DIALOG, directory=paths.settings()["export_dir"])
    return r[0] if r else None


def open_folder(p):
    p = str(p)
    if os.name == "nt":
        os.startfile(p)  # noqa
    elif sys.platform == "darwin":
        subprocess.Popen(["open", p])
    else:
        subprocess.Popen(["xdg-open", p])
    return True


def clipboard_get():
    """Read the Windows clipboard directly: the app window's own right-click menu can't rely on
    the browser clipboard API, which WebView2 may refuse without a permission prompt."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    u.GetClipboardData.restype = wintypes.HANDLE
    k.GlobalLock.restype = ctypes.c_void_p; k.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    CF_UNICODETEXT = 13
    for _ in range(10):
        if u.OpenClipboard(None):
            break
        import time; time.sleep(0.05)
    else:
        return None
    try:
        h = u.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        p = k.GlobalLock(h)
        try:
            return ctypes.wstring_at(p)
        finally:
            k.GlobalUnlock(h)
    finally:
        u.CloseClipboard()


def clipboard_set(text):
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    k.GlobalAlloc.restype = wintypes.HGLOBAL; k.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k.GlobalLock.restype = ctypes.c_void_p; k.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    u.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    data = (text + "\0").encode("utf-16-le")
    h = k.GlobalAlloc(0x0002, len(data))
    p = k.GlobalLock(h); ctypes.memmove(p, data, len(data)); k.GlobalUnlock(h)
    if not u.OpenClipboard(None):
        return False
    try:
        u.EmptyClipboard(); u.SetClipboardData(13, h)
    finally:
        u.CloseClipboard()
    return True


def restart():
    """Start a fresh copy (it waits for this one to let go of the single-instance lock), then quit."""
    exe = Path(sys.executable)
    if os.name == "nt" and exe.name.lower() == "python.exe" and exe.with_name("pythonw.exe").exists():
        exe = exe.with_name("pythonw.exe")
    args = [str(exe), "-m", "original_accent", "--wait-lock"] + (["--browser"] if WINDOW["w"] is None else [])
    subprocess.Popen(args, cwd=str(paths.APP), creationflags=paths.NO_WINDOW)

    def bye():
        import time
        time.sleep(0.4)
        try:
            if WINDOW["w"] is not None:
                WINDOW["w"].destroy()
        finally:
            os._exit(0)
    threading.Thread(target=bye, daemon=True).start()
    return True


def bg(fn, *a):
    if jobs.busy():
        raise RuntimeError("Something is already running.")
    threading.Thread(target=fn, args=a, daemon=True).start()
    return True


API = {
    "bootstrap": lambda a: {"settings": paths.settings(), "gpu": engines.gpu_info(), "engines": engines.status(),
                            "voices": jobs.voices(), "jobs": jobs.jobs(), "run": jobs.run_state(), "demo": paths.DEMO,
                            "ollama": engines.ollama_models(), "version": __import__("original_accent").__version__,
                            "choices": paths.read_json(paths.DATA / "install-choices.json")},
    "choices_clear": lambda a: (paths.DATA / "install-choices.json").unlink(missing_ok=True),
    "restart": lambda a: restart(),
    "clipboard_get": lambda a: clipboard_get(),
    "clipboard_set": lambda a: clipboard_set(a.get("text", "")),
    "suggest_trim": lambda a: jobs.suggest_trim(a["id"]),
    "full_peaks": lambda a: jobs.peaks(jobs.ensure_full(a["id"]), a.get("n", 1200)),
    "settings_save": lambda a: paths.save_settings(a),
    "gpu": lambda a: engines.gpu_info() | {"ollama": engines.ollama_models()},
    "gpu_mem": lambda a: engines.gpu_info(),
    "free_gpu": lambda a: {"unloaded": engines.free_gpu()},
    "engines": lambda a: engines.status(),
    "setup_install": lambda a: jobs.start_setup(a["engines"], bool(a.get("upgrade"))),
    "updates_check": lambda a: engines.check_updates(),
    "updates_last": lambda a: engines.last_updates(),
    "voices": lambda a: jobs.voices(),
    "voice_update": lambda a: jobs.update_voice(a["id"], a),
    "voice_transcribe": lambda a: bg(jobs.transcribe, a["id"]),
    "voice_peaks": lambda a: jobs.peaks(VOICES / a["id"] / "ref.wav", a.get("n", 400)),
    "jobs": lambda a: jobs.jobs(),
    "job_create": lambda a: jobs.create_job(a),
    "job_get": lambda a: jobs.job(a["id"]),
    "job_run": lambda a: jobs.start_run(a["id"]),
    "job_more": lambda a: jobs.more_takes(a["id"], int(a["part"]), int(a.get("n", 2))),
    "job_pick": lambda a: jobs.pick(a["id"], int(a["part"]), a["take"]),
    "job_export": lambda a: jobs.export(a["id"], a.get("dest"), a.get("separate", True), a.get("joined", False)),
    "take_peaks": lambda a: jobs.peaks(JOBS / a["job"] / "takes" / f"{a['take']}.wav", a.get("n", 400)),
    "run_state": lambda a: jobs.run_state(),
    "choose_folder": lambda a: choose_folder(),
    "open_folder": lambda a: open_folder(a["path"]),
}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)) or body is None or isinstance(body, bool):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, f):
        """Serves byte ranges by seeking, so the audio element can scrub a long recording
        without the whole file being read for every request."""
        f = Path(f)
        if not f.is_file():
            return self._send(404, {"error": "not found"})
        size = f.stat().st_size; ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        start, end, code = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            if a:
                start = int(a); end = min(int(b), size - 1) if b else size - 1
            else:
                start = max(0, size - int(b))
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", ctype); self.send_header("Accept-Ranges", "bytes")
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1)); self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with open(f, "rb") as fh:
            fh.seek(start); left = end - start + 1
            try:
                while left > 0:
                    chunk = fh.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk); left -= len(chunk)
            except (ConnectionResetError, BrokenPipeError):
                pass                                  # the player moved on; normal while scrubbing

    def _authed(self, q):
        return self.headers.get("X-Token") == TOKEN or q.get("t", [None])[0] == TOKEN

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query); parts = [unquote(p) for p in u.path.strip("/").split("/") if p]
        if not parts:
            html = (UI / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)
            return self._send(200, html, "text/html; charset=utf-8")
        if parts[0] == "ui":
            f = (UI / "/".join(parts[1:])).resolve()
            if UI.resolve() in f.parents:
                return self._file(f)
            return self._send(403, {"error": "forbidden"})
        if parts[0] == "media" and self._authed(q):
            if parts[1] == "voice" and len(parts) == 3:
                return self._file(VOICES / Path(parts[2]).name / "ref.wav")
            if parts[1] == "full" and len(parts) == 3:
                return self._file(jobs.ensure_full(Path(parts[2]).name))
            if parts[1] == "take" and len(parts) == 4:
                return self._file(JOBS / Path(parts[2]).name / "takes" / (Path(parts[3]).name + ".wav"))
        self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if not self._authed(q):
            return self._send(403, {"error": "forbidden"})
        n = int(self.headers.get("Content-Length") or 0)
        if u.path == "/upload":
            if n > jobs.MAX_UPLOAD:
                self.rfile.read(0)
                return self._send(200, {"ok": False, "error": "That file is over 4 GB. Trim it to the part with the speaker, or export just its audio, then add it."})
            tmp = paths.DATA / f"upload-{secrets.token_hex(4)}.part"
            with open(tmp, "wb") as f:              # streamed to disk in 1 MB pieces
                left = n
                while left > 0:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk:
                        break
                    f.write(chunk); left -= len(chunk)
            body = tmp
        else:
            body = self.rfile.read(n) if n else b""
        try:
            if u.path == "/upload":
                v = jobs.add_voice(q.get("name", [""])[0], q.get("filename", ["clip.wav"])[0], body,
                                   consent=q.get("consent", ["0"])[0] == "1")
                return self._send(200, v)
            name = u.path.removeprefix("/api/")
            if name not in API:
                return self._send(404, {"error": f"unknown call {name}"})
            args = json.loads(body or b"{}")
            return self._send(200, {"ok": True, "data": API[name](args)})
        except Exception as e:
            return self._send(200, {"ok": False, "error": str(e)})


def serve(port=0):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/"
