import argparse
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .models import Configuration, ConnectRequest, TestPlan
from .service import Lab
from .transport import ports

ROOT = Path(__file__).resolve().parent.parent


def create_app(demo=False, port=None, lab=None):
    lab = lab or Lab(ROOT/"data"/"tests")

    @asynccontextmanager
    async def lifespan(app):
        await lab.start(demo,port)
        yield
        await lab.close()

    app = FastAPI(title="ESP-NOW Funklabor",lifespan=lifespan)
    app.state.lab = lab

    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in ("GET","HEAD") and origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail":"Fremder Origin ist nicht erlaubt"},status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request,exc):
        return JSONResponse({"detail":str(exc)},status_code=409)

    @app.exception_handler(ConnectionError)
    @app.exception_handler(TimeoutError)
    @app.exception_handler(OSError)
    async def unavailable(request,exc):
        return JSONResponse({"detail":str(exc)},status_code=503)

    @app.get("/api/state")
    async def state():
        return lab.snapshot()

    @app.get("/api/ports")
    async def available_ports():
        return await asyncio.to_thread(ports)

    @app.post("/api/connect")
    async def connect(body: ConnectRequest):
        await lab.connect(body.port)
        return {"ok":True}

    @app.post("/api/disconnect")
    async def disconnect():
        if lab.active or lab.operation.locked():
            raise ValueError("Erst laufenden Versuch oder Konfigurationsänderung abschließen")
        await lab.disconnect()
        return {"ok":True}

    @app.post("/api/configure")
    async def configure(body: Configuration):
        return await lab.configure(body)

    @app.post("/api/tests")
    async def start_test(body: TestPlan):
        return await lab.start_test(body)

    @app.post("/api/tests/{tid}/stop")
    async def stop_test(tid:int):
        await lab.stop_test(tid)
        return {"ok":True}

    @app.get("/api/tests/{tid}/export")
    async def export(tid:int):
        run = lab.runs.get(tid)
        if not run:
            raise HTTPException(404,"Versuch nicht gefunden")
        return JSONResponse(run,headers={"Content-Disposition":f'attachment; filename="experiment-{tid}.json"'})

    @app.websocket("/ws")
    async def websocket(ws:WebSocket):
        if ws.headers.get("origin") not in (None, f"http://{ws.headers.get('host')}",f"https://{ws.headers.get('host')}"):
            await ws.close(code=1008)
            return
        await ws.accept()
        queue = asyncio.Queue(maxsize=1)
        lab.clients.add(queue)
        await queue.put({"type":"state","data":lab.snapshot()})
        try:
            while True:
                await ws.send_json(await queue.get())
        except (WebSocketDisconnect,RuntimeError,OSError):
            pass
        finally:
            lab.clients.discard(queue)

    app.mount("/",StaticFiles(directory=ROOT/"frontend",html=True),name="frontend")
    return app


app = create_app(demo=os.getenv("ESPLAB_DEMO") == "1",port=os.getenv("ESPLAB_PORT"))


def main():
    parser = argparse.ArgumentParser(description="ESP-NOW Funklabor (PC backend)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--demo",action="store_true",help="Explizite Simulation ohne Hardware")
    group.add_argument("--port",help="Serieller Master-Port, z. B. COM6")
    parser.add_argument("--http-port",type=int,default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(args.demo,args.port),host="127.0.0.1",port=args.http_port)


if __name__ == "__main__":
    main()
