"""Regenerates the README screenshots in demo mode (simulated engines): python scripts/screenshots.py"""
import os, subprocess, sys, tempfile
from pathlib import Path
import numpy as np, soundfile as sf
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"; OUT.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp())
env = dict(os.environ, OA_DEMO="1", OA_DATA=str(tmp / "data"), OA_EXPORTS=str(tmp / "exports"))
srv = subprocess.Popen([sys.executable, "-m", "original_accent", "--browser"], cwd=ROOT, env=env, stdout=subprocess.PIPE, text=True)
url = srv.stdout.readline().strip()
wav = tmp / "Narrator.wav"
sf.write(wav, (np.sin(np.arange(24000 * 20) / 24000 * 2 * np.pi * 150) * 0.2).astype("float32"), 24000)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        pg.goto(url); pg.wait_for_timeout(1000)
        pg.check("#consent"); pg.set_input_files("#file", str(wav)); pg.wait_for_timeout(2500)
        pg.click("text=Draft with Whisper"); pg.wait_for_timeout(2500)
        pg.evaluate("document.querySelectorAll('.toast').forEach(t=>t.remove())")
        pg.screenshot(path=str(OUT / "voice.png"))
        pg.click("[data-go=script]"); pg.fill("#jname", "Launch narration")
        pg.fill("[data-ptext='0']", "With the new card, I built a local multi-agent simulation where two teams attack and defend, all without the cloud.")
        pg.click("[data-act=generate]")
        for _ in range(120):
            if pg.locator(".cmp").count(): break
            pg.wait_for_timeout(500)
        pg.wait_for_timeout(800)
        for sk in ["grade", "reel", "signal", "booth"]:
            pg.evaluate(f"api('settings_save',{{skin:'{sk}'}}).then(s=>{{S.boot.settings=s;applySettings();render();}})")
            pg.wait_for_timeout(700); pg.evaluate("document.querySelectorAll('.toast').forEach(t=>t.remove())")
            pg.screenshot(path=str(OUT / f"compare-{sk}.png"))
        b.close()
finally:
    srv.terminate()
print("saved to", OUT)
