"""A stand-in for DaVinci Resolve's scripting API, used in demo mode (OA_DEMO=1) so the Resolve
features can be worked on and tested without Resolve. It implements only the calls
resolve_worker.py makes, with the same shapes, and logs what it was asked to do to
<OA_DATA>/demo-resolve.json."""
import json, math, os, struct, tempfile, wave
from pathlib import Path

LOG = Path(os.environ.get("OA_DATA", tempfile.gettempdir())) / "demo-resolve.json"
START = 86400                       # 01:00:00:00 at 24 fps


def _state():
    try:
        return json.loads(LOG.read_text())
    except Exception:
        return {"imported": [], "tracks": [], "placed": []}


def _save(s):
    LOG.write_text(json.dumps(s, indent=1))


def _demo_clip():
    p = Path(tempfile.gettempdir()) / "oa-demo-interview.wav"
    if not p.exists():
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
            w.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(i / 24000 * 2 * math.pi * 140) * abs(math.sin(i / 9000))))
                                   for i in range(24000 * 40)))
    return str(p)


class Item:
    def __init__(self, path, name=None):
        self.path, self.name = path, name or Path(path).name
    def GetName(self): return self.name
    def GetClipProperty(self, k):
        return {"File Path": self.path, "FPS": "24"}.get(k, "")
    def GetMarkInOut(self): return {"audio": {"in": 24 * 12, "out": 24 * 30 - 1}}


class TLItem:
    def __init__(self, mpi, start, end, src):
        self.mpi, self.start, self.end, self.src = mpi, start, end, src
    def GetMediaPoolItem(self): return self.mpi
    def GetStart(self): return self.start
    def GetEnd(self): return self.end
    def GetDuration(self): return self.end - self.start
    def GetLeftOffset(self): return self.src
    def GetSourceStartFrame(self): return self.src
    def GetSourceEndFrame(self): return self.src + (self.end - self.start) - 1


class Folder:
    def __init__(self, name): self.name, self.subs = name, []
    def GetName(self): return self.name
    def GetSubFolderList(self): return self.subs


class Pool:
    def __init__(self): self.root = Folder("Master")
    def GetRootFolder(self): return self.root
    def AddSubFolder(self, parent, name):
        f = Folder(name); parent.subs.append(f); return f
    def SetCurrentFolder(self, f): self.cur = f; return True
    def GetSelectedClips(self): return [Item(_demo_clip(), "Interview A-cam")]
    def ImportMedia(self, files):
        s = _state(); s["imported"] += files; _save(s)
        return [Item(f) for f in files if Path(f).exists()]
    def AppendToTimeline(self, infos):
        s = _state()
        for i in infos:
            s["placed"].append({"file": Path(i["mediaPoolItem"].path).name, "track": i["trackIndex"], "frame": i["recordFrame"]})
        _save(s); return [object() for _ in infos]


class Timeline:
    def __init__(self): self.audio = 2
    def GetName(self): return "Launch film v3"
    def GetSetting(self, k): return {"timelineFrameRate": "24", "timelineDropFrameTimecode": "0"}.get(k, "")
    def GetStartFrame(self): return START
    def GetCurrentTimecode(self): return "01:00:10:00"
    def GetMarkers(self):
        return {24 * 2: {"color": "Blue", "name": "Intro", "note": "This is the new ROG monitor.", "duration": 1},
                24 * 9: {"color": "Blue", "name": "", "note": "It runs at five hundred hertz.", "duration": 1},
                24 * 15: {"color": "Green", "name": "Graphics", "note": "", "duration": 1},
                24 * 20: {"color": "Blue", "name": "Outro", "note": "Available this spring.", "duration": 1}}
    def GetCurrentVideoItem(self): return TLItem(Item(_demo_clip(), "Interview A-cam"), START + 24 * 5, START + 24 * 25, 24 * 3)
    def GetTrackCount(self, kind): return self.audio if kind == "audio" else 1
    def GetItemListInTrack(self, kind, i): return []
    def AddTrack(self, kind, sub=None):
        self.audio += 1; s = _state(); s["tracks"].append(self.audio); _save(s); return True
    def SetTrackName(self, kind, i, name): return True


class Project:
    def __init__(self): self.pool, self.tl = Pool(), Timeline()
    def GetName(self): return "Demo project"
    def GetCurrentTimeline(self): return self.tl
    def GetMediaPool(self): return self.pool
    def GetSetting(self, k): return self.tl.GetSetting(k)


class PM:
    def __init__(self): self.p = Project()
    def GetCurrentProject(self): return self.p


class FakeResolve:
    def __init__(self): self.pm = PM()
    def GetProjectManager(self): return self.pm
    def GetProductName(self): return "DaVinci Resolve Studio (demo)"
    def GetVersionString(self): return "21.1.1"
