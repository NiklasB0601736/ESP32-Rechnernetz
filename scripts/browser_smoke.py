"""End-to-end UI check using installed Chrome and its local DevTools protocol.

Start `python -m backend.app --demo` first. No browser automation dependency.
"""
import asyncio
import base64
import json
import os
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

import websockets

ROOT=Path(__file__).resolve().parent.parent
ARTIFACTS=ROOT/"data"/"verification"


async def main():
    ARTIFACTS.mkdir(parents=True,exist_ok=True)
    chrome=Path(os.environ.get("PROGRAMFILES",r"C:\Program Files"))/"Google/Chrome/Application/chrome.exe"
    if not chrome.exists():
        raise SystemExit("Chrome fehlt. Pfad in scripts/browser_smoke.py anpassen.")
    chrome_log=(ARTIFACTS/"chrome.log").open("w",encoding="utf-8")
    profile=ROOT/"data"/f"browser-profile-{uuid.uuid4().hex[:8]}"
    profile.mkdir()
    process=subprocess.Popen([str(chrome),"--headless=new","--disable-gpu","--no-first-run","--enable-logging=stderr",
        "--no-default-browser-check","--disable-background-networking","--disable-extensions",
        "--disable-sync","--remote-debugging-port=0",f"--user-data-dir={profile}",
        "about:blank"],stdout=chrome_log,stderr=chrome_log,
        creationflags=subprocess.CREATE_NO_WINDOW)
    errors=[]
    print(f"Chrome test process: {process.pid}",flush=True)
    try:
        targets=[]
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError(f"Chrome exited: {process.returncode}; see {ARTIFACTS/'chrome.log'}")
            try:
                active=profile/"DevToolsActivePort"
                if not active.exists():
                    await asyncio.sleep(.1)
                    continue
                debug_port=int(active.read_text().splitlines()[0])
                with urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json",timeout=1) as response:
                    targets=json.load(response)
                if targets:break
            except OSError:
                pass
            await asyncio.sleep(.1)
        if not targets:
            raise RuntimeError(f"Chrome DevTools not available (exit={process.poll()})")
        print("Chrome DevTools connected",flush=True)
        page=next(t for t in targets if t["type"]=="page")
        async with websockets.connect(page["webSocketDebuggerUrl"],max_size=16000000) as ws:
            cid=0
            async def call(method,**params):
                nonlocal cid
                cid+=1;request_id=cid
                await ws.send(json.dumps(dict(id=request_id,method=method,params=params)))
                while True:
                    message=json.loads(await asyncio.wait_for(ws.recv(),30))
                    if message.get("method")=="Runtime.exceptionThrown":errors.append(message["params"])
                    if message.get("id")==request_id:
                        if "error" in message:raise RuntimeError(message["error"])
                        return message.get("result",{})
            async def evaluate(expression):
                result=await call("Runtime.evaluate",expression=expression,returnByValue=True,awaitPromise=True)
                if "exceptionDetails" in result:raise RuntimeError(result["exceptionDetails"])
                return result.get("result",{}).get("value")
            async def until(expression,timeout=12):
                end=time.monotonic()+timeout
                while time.monotonic()<end:
                    if await evaluate(expression):return
                    await asyncio.sleep(.15)
                raise AssertionError(f"Timed out: {expression}")
            await call("Runtime.enable")
            await call("Page.enable")
            await call("Emulation.setDeviceMetricsOverride",width=1440,height=1100,deviceScaleFactor=1,mobile=False)
            await call("Page.navigate",url="http://127.0.0.1:8000/")
            await until("typeof state!=='undefined' && state.mode==='simulation' && state.nodes.length===2 && !!charts.radar")
            print("Dashboard and four charts loaded",flush=True)
            before_change=await evaluate("state.changes[0]?.id||0")
            await evaluate("document.getElementById('power-node').value='1'; powerOptions(); document.getElementById('power').value='44'; document.getElementById('power-form').requestSubmit()")
            await until(f"state.changes[0]?.id!=={before_change} && state.changes[0]?.state==='success' && !locked")
            assert await evaluate("state.nodes.find(n=>n.node_id===1).power_qdbm===44 && state.nodes.find(n=>n.node_id===2).power_qdbm===72")
            before_change=await evaluate("state.changes[0]?.id||0")
            await evaluate("document.getElementById('profile').value='ofdm12';document.getElementById('profile-form').requestSubmit()")
            await until(f"state.changes[0]?.id!=={before_change} && state.changes[0]?.state==='success' && state.nodes.every(n=>n.profile==='ofdm12') && !locked")
            for source,destination in [(1,2),(2,1)]:
                before_run=await evaluate("state.runs.at(-1)?.id||0")
                await evaluate(f"document.getElementById('source').value='{source}';document.getElementById('destination').value='{destination}';document.getElementById('duration').value='2';document.getElementById('test-form').requestSubmit()")
                await until(f"state.runs.at(-1)?.id!=={before_run} && state.runs.at(-1)?.state==='complete' && state.runs.at(-1)?.plan.source==={source} && !locked")
            assert await evaluate("state.runs.at(-1).metrics.ber===null && charts.radar.data.datasets[0].data[0]===null")
            assert await evaluate("charts['goodput-chart'].data.datasets[0].data.length>1")
            assert await evaluate("document.getElementById('error').classList.contains('hidden')")
            desktop=await evaluate("({nodes:document.querySelectorAll('#nodes tr').length,charts:Object.keys(charts).length,bodyWidth:document.body.scrollWidth,viewport:innerWidth,ber:document.querySelector('#metrics .metric:last-child strong').textContent,run:state.runs.at(-1)})")
            assert desktop["bodyWidth"]<=desktop["viewport"],desktop
            screenshot=await call("Page.captureScreenshot",format="png",captureBeyondViewport=True)
            (ARTIFACTS/"dashboard-desktop.png").write_bytes(base64.b64decode(screenshot["data"]))
            await call("Emulation.setDeviceMetricsOverride",width=390,height=844,deviceScaleFactor=1,mobile=True)
            await asyncio.sleep(.4)
            mobile=await evaluate("({bodyWidth:document.body.scrollWidth,viewport:innerWidth})")
            assert mobile["bodyWidth"]<=mobile["viewport"],mobile
            screenshot=await call("Page.captureScreenshot",format="png",captureBeyondViewport=True)
            (ARTIFACTS/"dashboard-mobile.png").write_bytes(base64.b64decode(screenshot["data"]))
            assert not errors,errors
            result=dict(ok=True,desktop=desktop,mobile=mobile,javascript_errors=errors)
            (ARTIFACTS/"browser-test.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps(dict(ok=True,nodes=desktop["nodes"],charts=desktop["charts"],mobile=mobile,javascript_errors=len(errors))))
            await call("Browser.close")
    finally:
        process.terminate()
        try:process.wait(timeout=8)
        except subprocess.TimeoutExpired:process.kill()
        chrome_log.close()


if __name__=="__main__":
    asyncio.run(main())
