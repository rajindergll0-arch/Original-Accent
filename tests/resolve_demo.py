"""DaVinci Resolve bridge, end to end, without Resolve.

Studio route: the app talks to workers/resolve_fake.py (demo mode stands in for Resolve).
Free route: the real Lua menu scripts are run with LuaJIT against tests/resolve_fake.lua,
the way Resolve would run them from Workspace > Scripts. Needs luajit on PATH.
Checks: voice from a clip, script from markers, takes placed at their markers and at the
playhead, nothing outside its box, no page errors."""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).parent))
from smoke_demo_check import CHECK

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp()); data = tmp / "data"
env = dict(os.environ, OA_DEMO="1", OA_DATA=str(data), OA_EXPORTS=str(tmp / "exports"), OA_NO_OPEN="1")
srv = subprocess.Popen([sys.executable, "-m", "original_accent", "--browser"], cwd=ROOT, env=env, stdout=subprocess.PIPE, text=True)
url = srv.stdout.readline().strip()
LUA_DIR = data / "demo-appdata" / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Scripts" / "Utility"


def run_menu(name):
    """What choosing Workspace > Scripts > <name> in Resolve does."""
    clip = Path(tempfile.gettempdir()) / "oa-demo-interview.wav"
    if not clip.exists():
        shutil.copy(next((data / "voices").glob("*/full.wav")), clip)
    out = subprocess.run(["luajit", "-e", f'dofile("{ROOT / "tests" / "resolve_fake.lua"}")', str(LUA_DIR / f"{name}.lua")],
                         env=dict(os.environ, OA_BRIDGE_DIR=str(data / "resolve") + "/", OA_TEST_CLIP=str(clip)),
                         capture_output=True, text=True)
    assert "done" in out.stdout, out.stdout + out.stderr


def run_console(line):
    """What pasting the app's line into Resolve's Console (Py3) does, with Resolve's `resolve` object."""
    code = ("import sys;sys.path.insert(0,%r);from resolve_fake import FakeResolve;resolve=FakeResolve();" % str(ROOT / "workers")) + line
    out = subprocess.run([sys.executable, "-c", code], env=dict(os.environ, OA_DEMO="1", OA_DATA=str(data),
                         LOCALAPPDATA=str(tmp / "la"), OA_BRIDGE_DIR=str(data / "resolve")), capture_output=True, text=True)
    assert "done" in out.stdout, out.stdout + out.stderr


def shot(pg, name):
    if os.environ.get("OA_SHOTS"):
        pg.screenshot(path=str(Path(os.environ["OA_SHOTS"]) / f"{name}.png"), full_page=True)


def wait(pg, js, what, n=120):
    for _ in range(n):
        if pg.evaluate(js):
            return
        pg.wait_for_timeout(250)
    raise AssertionError(f"timed out waiting for {what}")


errors, problems = [], {}
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1366, "height": 860})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url); pg.wait_for_timeout(1000)

        # ---------- Studio route
        pg.click("[data-go=settings]"); pg.click("[data-act=r-test]")
        wait(pg, "S.rlive && S.rlive.ok", "connection test")
        problems["settings-studio"] = pg.evaluate(CHECK); shot(pg, "settings")
        pg.click("[data-go=voice]"); pg.check("#consent"); pg.click("[data-act=r-voice][data-which=playhead]")
        wait(pg, "S.boot.voices.length === 1", "voice from the clip at the playhead")
        v = pg.evaluate("S.boot.voices[0]"); assert v["from_resolve"] == "the part used in the timeline" and v["trim"], v
        problems["voice"] = pg.evaluate(CHECK)
        pg.evaluate("api('voice_update',{id:S.voiceId,transcript:'Hello there.'}).then(nv=>{replaceVoice(nv);render()})")
        pg.click("[data-go=script]"); pg.click("[data-act=r-markers]")
        wait(pg, "!!S.rmark", "markers")
        problems["markers-panel"] = pg.evaluate(CHECK); shot(pg, "markers")
        pg.click("[data-act=r-use-markers]")
        parts = pg.evaluate("draft().parts")
        assert [x["at"]["tc"] for x in parts] == ["01:00:02:00", "01:00:09:00", "01:00:20:00"], parts
        problems["script"] = pg.evaluate(CHECK)
        pg.click("[data-act=generate]")
        wait(pg, "document.querySelector('.cmp')", "Compare", 240)
        pg.evaluate("(async()=>{for(let i=0;i<S.job.parts.length;i++){S.job=await api('job_pick',{id:S.jobId,part:i,take:S.job.takes.find(t=>t.part===i).id})} render()})()")
        pg.wait_for_timeout(1200); pg.click("[data-go=deliver]"); pg.wait_for_timeout(300)
        problems["deliver"] = pg.evaluate(CHECK); shot(pg, "deliver")
        pg.click("[data-act=r-send]"); wait(pg, "!!S.rsent", "send at markers")
        log = json.loads((data / "demo-resolve.json").read_text())
        assert [x["frame"] for x in log["placed"]] == [86448, 86616, 86880], log
        pg.check("input[name=rplace][value=playhead]"); pg.click("[data-act=r-send]"); wait(pg, "!!S.rsent", "send at playhead")
        log = json.loads((data / "demo-resolve.json").read_text())
        assert log["placed"][-1]["frame"] == 86640 and log["placed"][-1]["file"].endswith("_complete.wav"), log["placed"][-1]

        # ---------- Free route
        pg.click("[data-go=settings]"); pg.check("input[name=rmode][value=free]"); pg.wait_for_timeout(500)
        assert (LUA_DIR / "Original Accent - Bring in takes.lua").exists(), "menu scripts not installed"
        problems["settings-free"] = pg.evaluate(CHECK)
        pg.click("[data-go=voice]"); pg.check("#consent"); pg.click("[data-act=r-voice][data-which=selected]")
        wait(pg, "!!S.rwait", "waiting box"); problems["voice-waiting"] = pg.evaluate(CHECK); shot(pg, "voice-waiting")
        run_menu("Original Accent - Send selected clip")
        wait(pg, "S.boot.voices.length === 2", "voice from the selected clip")
        v = pg.evaluate("S.boot.voices.find(x=>x.id===S.voiceId)"); assert v["from_resolve"] == "its In and Out marks", v
        pg.evaluate("api('voice_update',{id:S.voiceId,transcript:'Hello there.'}).then(nv=>{replaceVoice(nv);render()})")
        pg.click("[data-go=script]"); pg.evaluate("S.draft=null;render()"); pg.click("[data-act=r-markers]")
        wait(pg, "!!S.rwait", "waiting for markers"); problems["script-waiting"] = pg.evaluate(CHECK)
        run_console(pg.evaluate("S.rwait.console"))
        wait(pg, "!!S.rmark", "markers through the menu"); pg.click("[data-act=r-use-markers]")
        assert len(pg.evaluate("draft().parts")) == 3
        pg.click("[data-act=generate]")
        wait(pg, "document.querySelector('.cmp')", "Compare", 240)
        pg.evaluate("(async()=>{for(let i=0;i<S.job.parts.length;i++){S.job=await api('job_pick',{id:S.jobId,part:i,take:S.job.takes.find(t=>t.part===i).id})} render()})()")
        pg.wait_for_timeout(1200); pg.click("[data-go=deliver]"); pg.wait_for_timeout(300)
        pg.check("input[name=rplace][value=markers]")
        pg.click("[data-act=r-send]"); wait(pg, "!!S.rwait", "waiting to bring in takes")
        problems["deliver-waiting"] = pg.evaluate(CHECK)
        run_console(pg.evaluate("S.rwait.console"))
        wait(pg, "!!S.rsent", "takes brought in"); sent = pg.evaluate("S.rsent")
        assert "3 placed" in sent, (sent, pg.evaluate("S.job.picks"), pg.evaluate("S.job.parts"))
        pg.screenshot(path=str(tmp / "deliver.png"))
        b.close()
finally:
    srv.terminate()
bad = {k: v for k, v in problems.items() if v}
print("pages:", ", ".join(problems))
if errors or bad:
    print("page errors:", errors); print("layout problems:", bad); sys.exit(1)
print("OK", tmp / "deliver.png")
