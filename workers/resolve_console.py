"""Run from DaVinci Resolve's Console (Py3) when Resolve won't run scripts any other way
(Resolve 21.1 free keeps console scripting only). The app gives the operator one line to paste:

    import importlib,sys;sys.path.insert(0,r"<workers>");import resolve_console as c;importlib.reload(c);c.run(globals(),"takes")

It does the same jobs as the Lua menu scripts, with the same operations the Studio route uses
(resolve_worker.py), against the `resolve` object the Console already has, and swaps the
same files with the app in %LOCALAPPDATA%\\OriginalAccent\\resolve.
"""
import json, os, time, traceback
from pathlib import Path
import resolve_worker as W

BRIDGE = Path(os.environ.get("OA_BRIDGE_DIR") or Path(os.environ.get("LOCALAPPDATA", "")) / "OriginalAccent" / "resolve")


def _log(line):
    try:
        with open(BRIDGE / "script-log.txt", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "  " + line + "\n")
    except OSError:
        pass


def _write(name, msg):
    tmp = BRIDGE / (name + ".part")
    tmp.write_text(json.dumps(msg), encoding="utf-8")
    os.replace(tmp, BRIDGE / name)


def run(g, kind):
    print(f"Original Accent: running ({kind})…")
    _log("start " + kind)
    name = "outbox-result.json" if kind == "takes" else ("inbox-markers.json" if kind == "markers" else "inbox-clip.json")
    try:
        r = g.get("resolve") or (g["bmd"].scriptapp("Resolve") if "bmd" in g else None)
        if r is None:
            raise W.Problem("Run this from DaVinci Resolve's Console (Workspace > Console, Py3).")
        if kind == "markers":
            out = W.op_markers(r, {})
        elif kind in ("selected", "playhead"):
            out = W.op_clip(r, {"which": kind})
        else:
            f = BRIDGE / "outbox.json"
            if not f.exists():
                raise W.Problem("Nothing to bring in. In Original Accent, press Send to Resolve on the Deliver page first.")
            req = json.loads(f.read_text(encoding="utf-8"))
            out = W.op_send(r, req)
            out["id"] = req.get("id")
            f.unlink()                         # done: running it again won't import twice
            (BRIDGE / "outbox.lua").unlink(missing_ok=True)
        out["ok"] = True
        _write(name, out)
        _log("done " + kind)
        print("Original Accent: done. Switch back to Original Accent.")
    except W.Problem as e:
        _write(name, {"ok": False, "error": str(e)}); _log(f"error {kind}: {e}"); print("Original Accent: " + str(e))
    except Exception as e:
        msg = f"Resolve reported a problem: {type(e).__name__}: {e}"
        _write(name, {"ok": False, "error": msg}); _log(f"error {kind}: {msg}")
        print("Original Accent: " + msg); traceback.print_exc()
