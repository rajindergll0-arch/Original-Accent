"""Talks to DaVinci Resolve through its scripting API. Run by the app as a separate process
(so a problem in Resolve's library can never take the app down), one request per run:

    python resolve_worker.py  < {"op": "...", ...}      ->  one JSON line on stdout

Needs DaVinci Resolve Studio running with Preferences > System > General >
"External scripting using" set to Local. (From 21.1, scripting is a Studio feature.)
With OA_DEMO=1 a simulated Resolve is used instead, so the UI and tests work anywhere.

Frames: Resolve's timeline API works in timeline frames. Marker positions are offsets from
the timeline's start; recordFrame for placement is absolute (start frame + offset).
"""
import json, os, sys
from pathlib import Path

DEFAULT_DIR = r"C:\Program Files\Blackmagic Design\DaVinci Resolve"
HELP = ("Couldn't reach DaVinci Resolve. Check that Resolve Studio is open with a project, and that "
        "Preferences > System > General > External scripting using is set to Local. "
        "From Resolve 21.1, scripting needs the Studio edition.")


class Problem(Exception):
    pass


# ------------------------------------------------------------------ connecting

def resolve_dir():
    return Path(os.environ.get("OA_RESOLVE_DIR") or DEFAULT_DIR)


def connect():
    if os.environ.get("OA_DEMO"):
        from resolve_fake import FakeResolve
        return FakeResolve()
    lib = Path(os.environ.get("RESOLVE_SCRIPT_LIB") or resolve_dir() / "fusionscript.dll")
    if not lib.exists():
        raise Problem(f"DaVinci Resolve isn't installed where expected ({lib.parent}).")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(lib.parent))     # fusionscript loads Resolve's own DLLs
    import importlib.machinery, importlib.util
    loader = importlib.machinery.ExtensionFileLoader("fusionscript", str(lib))
    spec = importlib.util.spec_from_loader("fusionscript", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    r = mod.scriptapp("Resolve")
    if r is None:
        raise Problem(HELP)
    return r


def context(r, need_timeline=True):
    pm = r.GetProjectManager()
    project = pm.GetCurrentProject() if pm else None
    if not project:
        raise Problem("Resolve has no project open.")
    tl = project.GetCurrentTimeline()
    if need_timeline and not tl:
        raise Problem("Open a timeline in Resolve first.")
    return project, tl


def fps_of(project, tl):
    v = (tl.GetSetting("timelineFrameRate") if tl else None) or project.GetSetting("timelineFrameRate") or "24"
    try:
        return float(str(v).split()[0])
    except ValueError:
        return 24.0


def drop_frame(tl, project):
    v = (tl.GetSetting("timelineDropFrameTimecode") if tl else None) or project.GetSetting("timelineDropFrameTimecode")
    return str(v) in ("1", "True", "true")


# ------------------------------------------------------------------ timecode

def tc_to_frames(tc, fps):
    """Absolute frame number of a timecode. Handles drop-frame (';') at 29.97 and 59.94."""
    df = ";" in tc
    h, m, s, f = (int(x) for x in tc.replace(";", ":").split(":"))
    nom = round(fps)
    total = ((h * 60 + m) * 60 + s) * nom + f
    if df:
        drop = 2 if nom == 30 else 4
        mins = h * 60 + m
        total -= drop * (mins - mins // 10)
    return total


def frames_to_tc(n, fps, df=False):
    nom = round(fps)
    if df:
        drop = 2 if nom == 30 else 4
        per10 = nom * 600 - drop * 9
        d, mrem = divmod(n, per10)
        n += drop * 9 * d + (drop * ((mrem - drop) // (nom * 60 - drop)) if mrem > drop else 0)
    f = n % nom; s = (n // nom) % 60; m = (n // (nom * 60)) % 60; h = n // (nom * 3600)
    return f"{h:02d}:{m:02d}:{s:02d}{';' if df else ':'}{f:02d}"


# ------------------------------------------------------------------ operations

def op_status(r, a):
    out = {"ok": True, "product": r.GetProductName(), "version": r.GetVersionString()}
    pm = r.GetProjectManager()
    project = pm.GetCurrentProject() if pm else None
    out["project"] = project.GetName() if project else None
    tl = project.GetCurrentTimeline() if project else None
    out["timeline"] = tl.GetName() if tl else None
    if tl:
        out["fps"] = fps_of(project, tl)
        out["playhead"] = tl.GetCurrentTimecode()
    return out


def _clip_fps(mpi, default):
    try:
        return float(str(mpi.GetClipProperty("FPS")).split()[0]) or default
    except Exception:
        return default


def op_clip(r, a):
    """The file behind a clip, and the part of it to use.
    selected: the clip selected in the Media Pool, using its In/Out marks if set.
    playhead: the clip under the playhead on the timeline (top video track first, then audio),
              using the part of the source that's actually in the edit."""
    project, tl = context(r, need_timeline=a.get("which") == "playhead")
    fps = fps_of(project, tl)
    if a.get("which") == "playhead":
        item = tl.GetCurrentVideoItem()
        if item is None or item.GetMediaPoolItem() is None:
            here = tc_to_frames(tl.GetCurrentTimecode(), fps)
            item = None
            for i in range(1, (tl.GetTrackCount("audio") or 0) + 1):
                for it in tl.GetItemListInTrack("audio", i) or []:
                    if it.GetStart() <= here < it.GetEnd() and it.GetMediaPoolItem() is not None:
                        item = it; break
                if item:
                    break
        if item is None:
            raise Problem("There's no clip under the playhead. Move the playhead onto the speaker's clip.")
        mpi = item.GetMediaPoolItem()
        cfps = _clip_fps(mpi, fps)
        try:
            s0, s1 = item.GetSourceStartFrame(), item.GetSourceEndFrame()
            a_s, b_s = s0 / cfps, (s1 + 1) / cfps
        except Exception:
            a_s = item.GetLeftOffset() / fps
            b_s = a_s + item.GetDuration() / fps
        rng, how = [round(a_s, 3), round(b_s, 3)], "the part used in the timeline"
    else:
        sel = project.GetMediaPool().GetSelectedClips() or []
        sel = list(sel.values()) if isinstance(sel, dict) else list(sel)
        if not sel:
            raise Problem("Select the speaker's clip in Resolve's Media Pool first.")
        mpi = sel[0]
        cfps = _clip_fps(mpi, fps)
        rng, how = None, "the whole clip"
        try:
            mk = mpi.GetMarkInOut() or {}
            io = mk.get("audio") or mk.get("video") or {}
            if "in" in io and "out" in io and io["out"] > io["in"]:
                rng, how = [round(io["in"] / cfps, 3), round((io["out"] + 1) / cfps, 3)], "its In and Out marks"
        except Exception:
            pass
    path = mpi.GetClipProperty("File Path")
    if not path:
        raise Problem("That clip has no file on disk Original Accent can read (for example, a generator or compound clip).")
    return {"ok": True, "path": path, "name": mpi.GetName(), "range": rng, "how": how}


def op_markers(r, a):
    project, tl = context(r)
    fps, start, df = fps_of(project, tl), tl.GetStartFrame(), drop_frame(tl, project)
    out = []
    for off, m in sorted((tl.GetMarkers() or {}).items(), key=lambda kv: float(kv[0])):
        off = int(float(off))
        out.append({"frame": start + off, "tc": frames_to_tc(start + off, fps, df), "color": m.get("color", ""),
                    "name": m.get("name", ""), "note": m.get("note", ""), "duration": m.get("duration", 1)})
    return {"ok": True, "timeline": tl.GetName(), "fps": fps, "markers": out}


def _bin(pool, path):
    folder = pool.GetRootFolder()
    for name in path:
        nxt = next((f for f in (folder.GetSubFolderList() or []) if f.GetName() == name), None)
        folder = nxt or pool.AddSubFolder(folder, name)
        if folder is None:
            raise Problem(f"Couldn't create the bin “{name}” in the Media Pool.")
    return folder


def op_send(r, a):
    """Import files into a bin; optionally place some on new audio tracks.
    a = {bin: [names], files: [paths], place: [{file, frame (absolute) | at: "playhead", seconds}],
         track: "name"}. Placed clips never go on existing tracks: new tracks are added, and a
    clip that would overlap the one before it goes on a further new track."""
    project, tl = context(r, need_timeline=bool(a.get("place")))
    pool = project.GetMediaPool()
    folder = _bin(pool, a["bin"])
    pool.SetCurrentFolder(folder)
    items = pool.ImportMedia(a["files"]) or []
    if len(items) != len(a["files"]):
        raise Problem(f"Resolve imported {len(items)} of {len(a['files'])} files.")
    by_file = {}
    for f, it in zip(a["files"], items):
        by_file[os.path.normcase(os.path.abspath(f))] = it
    placed, tracks = [], []
    if a.get("place"):
        fps = fps_of(project, tl)
        here = tc_to_frames(tl.GetCurrentTimecode(), fps)
        ends = []                                  # last end frame on each new track
        for p in sorted(a["place"], key=lambda p: p.get("frame") or 0):
            start = here + round(p.get("offset", 0) * fps) if p.get("at") == "playhead" else int(p["frame"])
            end = start + max(1, round(p["seconds"] * fps))
            k = next((i for i, e in enumerate(ends) if e <= start), None)
            if k is None:
                if not tl.AddTrack("audio", "mono"):
                    raise Problem("Resolve wouldn't add an audio track.")
                idx = tl.GetTrackCount("audio")
                try:
                    tl.SetTrackName("audio", idx, a.get("track", "Original Accent") + (f" {len(ends) + 1}" if ends else ""))
                except Exception:
                    pass
                tracks.append(idx); ends.append(end); k = len(ends) - 1
            else:
                ends[k] = end
            it = by_file[os.path.normcase(os.path.abspath(p["file"]))]
            res = pool.AppendToTimeline([{"mediaPoolItem": it, "mediaType": 2, "trackIndex": tracks[k], "recordFrame": start}])
            if not res:
                raise Problem(f"Resolve wouldn't place {Path(p['file']).name} on the timeline.")
            placed.append({"file": Path(p["file"]).name, "tc": frames_to_tc(start, fps, drop_frame(tl, project)), "track": tracks[k]})
    return {"ok": True, "imported": len(items), "bin": "/".join(a["bin"]), "placed": placed, "tracks": tracks,
            "timeline": tl.GetName() if tl else None}


OPS = {"status": op_status, "clip": op_clip, "markers": op_markers, "send": op_send}


def main():
    a = json.loads(sys.stdin.read() or "{}")
    try:
        out = OPS[a["op"]](connect(), a)
    except Problem as e:
        out = {"ok": False, "error": str(e)}
    except Exception as e:                       # report Resolve's own errors plainly
        out = {"ok": False, "error": f"Resolve reported a problem: {type(e).__name__}: {e}"}
    sys.stdout.write(json.dumps(out) + "\n")


if __name__ == "__main__":
    main()
