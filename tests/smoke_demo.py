"""End-to-end UI check with simulated engines (OA_DEMO=1): add a voice, draft its transcript,
write a two-part script, generate, look at Compare in every skin, pick, export one joined file.
Fails on any page error, any text outside its box, or sideways scrolling."""
import os, subprocess, sys, tempfile, time
from pathlib import Path
import numpy as np, soundfile as sf
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp())
env = dict(os.environ, OA_DEMO="1", OA_DATA=str(tmp / "data"), OA_EXPORTS=str(tmp / "exports"), OA_NO_OPEN="1")
srv = subprocess.Popen([sys.executable, "-m", "original_accent", "--browser"], cwd=ROOT, env=env,
                       stdout=subprocess.PIPE, text=True)
url = srv.stdout.readline().strip()
wav = tmp / "speaker.wav"
sf.write(wav, (np.sin(np.arange(24000 * 20) / 24000 * 2 * np.pi * 150) * 0.2).astype("float32"), 24000)
CHECK = """()=>{const box=['panel','clip','strip','item','btn','notice','toast','takes','stage','track','scope','tag','field','hero','top','navbtn','erow'];
 const out=[]; const m=document.querySelector('#main'); if(m.scrollWidth>m.clientWidth+2) out.push('sideways scroll');
 for(const el of document.querySelectorAll('#main *')){ if(el.closest('.pv')||!el.offsetParent) continue;
  if(![...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())) continue;
  const r=el.getBoundingClientRect(); let a=el.parentElement; while(a&&!box.some(c=>a.classList&&a.classList.contains(c))) a=a.parentElement;
  if(!a||!r.width) continue; const b=a.getBoundingClientRect();
  if(getComputedStyle(el).textOverflow!=='ellipsis'&&(r.right>b.right+1.5||r.left<b.left-1.5)) out.push(el.textContent.trim().slice(0,40));}
 return out}"""
errors, problems = [], {}
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1366, "height": 800})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url); pg.wait_for_timeout(1000)
        pg.check("#consent"); pg.set_input_files("#file", str(wav)); pg.wait_for_timeout(2500)
        pg.click("text=Draft with Whisper"); pg.wait_for_timeout(2500)
        problems["voice"] = pg.evaluate(CHECK)
        pg.click("[data-go=script]"); pg.fill("#jname", "Smoke test")
        pg.fill("[data-ptext='0']", "Every frame matters when you're this close to the finish line.")
        pg.click("text=+ Add part"); pg.fill("[data-ptext='1']", "Clustering two units isn't about one big chatbot.")
        problems["script"] = pg.evaluate(CHECK)
        pg.click("[data-act=generate]")
        for _ in range(120):
            if pg.locator(".cmp").count(): break
            pg.wait_for_timeout(500)
        assert pg.locator(".cmp").count(), "Compare never appeared"
        for sk in ["grade", "reel", "signal", "booth"]:
            pg.evaluate(f"api('settings_save',{{skin:'{sk}'}}).then(s=>{{S.boot.settings=s;applySettings();render();}})")
            pg.wait_for_timeout(600); problems[f"compare-{sk}"] = pg.evaluate(CHECK)
        pg.evaluate("(async()=>{for(let i=0;i<S.job.parts.length;i++){S.job=await api('job_pick',{id:S.jobId,part:i,take:S.job.takes.find(t=>t.part===i).id})} render()})()")
        pg.wait_for_timeout(1500); pg.click("[data-go=deliver]"); pg.wait_for_timeout(400)
        pg.click("[data-act=export]"); pg.wait_for_timeout(2500)
        problems["deliver"] = pg.evaluate(CHECK)
        files = pg.evaluate("S.exportResult && S.exportResult.files")
        b.close()
finally:
    srv.terminate()
bad = {k: v for k, v in problems.items() if v}
print("pages:", ", ".join(problems), "| files exported:", len(files or []))
if errors or bad or not files or not any(f.endswith("_complete.wav") for f in files):
    print("page errors:", errors); print("layout problems:", bad); print("files:", files)
    sys.exit(1)
print("OK")
