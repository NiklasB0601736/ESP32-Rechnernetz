import asyncio
import json
import secrets
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from .metrics import evaluate, validate_report
from .models import PROFILES
from .simulator import Simulator
from .transport import SerialTransport


def utc():
    return datetime.now(timezone.utc).isoformat()


class Lab:
    def __init__(self, data_dir=Path("data/tests")):
        self.nodes = {}
        self.runs = {}
        self.active = None
        self.transport = None
        self.mode = "disconnected"
        self.connection_error = None
        self.events = deque(maxlen=80)
        self.changes = deque(maxlen=40)
        self.clients = set()
        self.pending = {}
        self.command_id = secrets.randbelow(1000000000)+1
        self.operation = asyncio.Lock()
        self.data_dir = Path(data_dir)
        self.tick_task = None
        self.dirty = True

    def log(self, message, level="info"):
        self.events.appendleft(dict(at=utc(), level=level, message=message))
        self.dirty = True

    def snapshot(self):
        now = time.monotonic()
        nodes = [{**n, "online": self.mode != "disconnected" and now-n["_seen"] < 4}
                 for n in self.nodes.values()]
        for n in nodes:
            n.pop("_seen", None)
        common = set(PROFILES)
        if not nodes:
            common.clear()
        for n in nodes:
            common &= set(n.get("profiles", []))
        edges = sorted({tuple(sorted((n["node_id"], n["peer_id"]))) for n in nodes if n.get("peer_id")})
        return dict(mode=self.mode, connection_error=self.connection_error, nodes=nodes,
                    profiles=[dict(id=p, **PROFILES[p]) for p in PROFILES if p in common],
                    edges=edges, active=self.active, runs=list(self.runs.values())[-30:],
                    changes=list(self.changes), events=list(self.events))

    async def start(self, demo=False, port=None):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.data_dir.glob("*.json"),key=lambda p:p.stat().st_mtime)[-30:]:
            try:
                run = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(run, dict) and "id" in run:
                    self.runs[run["id"]] = run
            except (ValueError, OSError):
                self.log(f"Archiv konnte nicht gelesen werden: {path.name}", "error")
        if demo or port:
            await self.connect(port, demo)
        self.tick_task = asyncio.create_task(self.tick())

    async def connect(self, port=None, demo=False):
        if self.active or self.operation.locked():
            raise ValueError("Verbindung während Versuch oder Konfigurationsänderung gesperrt")
        await self.disconnect()
        self.nodes.clear()
        self.transport = Simulator(self.receive) if demo else SerialTransport(port, self.receive, self.disconnected)
        try:
            await self.transport.start()
        except Exception:
            self.transport = None
            raise
        self.mode = "simulation" if demo else "hardware"
        self.connection_error = None
        self.log("Simulation verbunden" if demo else f"Gateway auf {port} verbunden")

    async def disconnected(self, reason):
        self.mode = "disconnected"
        self.connection_error = reason
        self.log(f"Serielle Verbindung verloren: {reason}", "error")
        for future in list(self.pending.values()):
            if not future.done():
                future.set_exception(ConnectionError(reason))

    async def disconnect(self):
        if self.transport:
            await self.transport.close()
            self.transport = None
        self.mode = "disconnected"
        self.dirty = True

    async def close(self):
        if self.tick_task:
            self.tick_task.cancel()
            try:
                await self.tick_task
            except asyncio.CancelledError:
                pass
        await self.disconnect()

    def next_id(self):
        self.command_id = self.command_id % 0xFFFFFFFE + 1
        return self.command_id

    async def command(self, node_id, op, command_id=None, **fields):
        if not self.transport or self.mode == "disconnected":
            raise ConnectionError("Kein Gateway verbunden")
        cid = command_id or self.next_id()
        future = asyncio.get_running_loop().create_future()
        self.pending[(cid, node_id, op)] = future
        message = dict(v=1, id=cid, node_id=node_id, op=op, **fields)
        try:
            for _ in range(4):
                await self.transport.send(message)
                try:
                    reply = await asyncio.wait_for(asyncio.shield(future), .7)
                    if not reply.get("ok"):
                        raise ValueError(reply.get("error", f"Knoten {node_id}: {op} abgelehnt"))
                    return reply
                except asyncio.TimeoutError:
                    continue
            raise TimeoutError(f"Knoten {node_id}: keine Bestätigung für {op}")
        finally:
            self.pending.pop((cid, node_id, op), None)
            if not future.done():
                future.cancel()

    def require_nodes(self, ids):
        if self.mode == "disconnected":
            raise ValueError("Kein Gateway verbunden")
        for nid in ids:
            n = self.nodes.get(nid)
            if not n or time.monotonic()-n["_seen"] >= 4:
                raise ValueError(f"Knoten {nid} ist offline")

    async def configure(self, request):
        if self.operation.locked() or self.active:
            raise ValueError("Während eines Versuchs oder einer Änderung gesperrt")
        async with self.operation:
            all_ids = set(self.nodes)
            powers = {int(k): v for k, v in request.powers.items()}
            targets = all_ids if request.profile is not None else set(powers)
            if not targets:
                raise ValueError("Keine Änderung angefordert")
            self.require_nodes(targets)
            if request.profile is not None:
                common = {p["id"] for p in self.snapshot()["profiles"]}
                if request.profile not in common:
                    raise ValueError("PHY-Profil wird nicht von allen Knoten unterstützt")
            if not set(powers) <= all_ids:
                raise ValueError("Unbekannte Knoten-ID")
            for nid, power in powers.items():
                if power not in self.nodes[nid].get("powers_qdbm", []):
                    raise ValueError(f"Knoten {nid}: Leistungsstufe nicht unterstützt")
            txn = self.next_id()
            change = dict(id=txn, at=utc(), state="pending", requested=dict(powers=powers, profile=request.profile))
            self.changes.appendleft(change)
            self.dirty = True
            expected = {nid: dict(power_qdbm=powers.get(nid,self.nodes[nid]["power_qdbm"]),
                                  profile=request.profile or self.nodes[nid]["profile"]) for nid in targets}
            configured_at = time.monotonic()
            try:
                for nid, config in expected.items():
                    await self.command(nid, "configure", command_id=txn, lease_ms=15000, **config)
                # Health is proved by fresh status on the changed link after application, in both directions.
                deadline = time.monotonic()+6
                while True:
                    healthy = all(self.nodes[nid]["_seen"] > configured_at+1.5 and
                                  self.nodes[nid].get("link_healthy") and
                                  all(self.nodes[nid].get(k) == v for k,v in cfg.items())
                                  for nid,cfg in expected.items())
                    if healthy:
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Funkverbindung nach Änderung nicht bestätigt")
                    await asyncio.sleep(.1)
                for nid in targets:
                    await self.command(nid, "commit", transaction=txn)
                change.update(state="success", confirmed=expected)
                self.log(f"Konfiguration {txn} bestätigt")
            except (ValueError, ConnectionError, TimeoutError, OSError) as exc:
                change.update(state="failed", error=str(exc))
                for nid in targets:
                    try:
                        await self.command(nid, "rollback", transaction=txn)
                    except (ValueError, ConnectionError, TimeoutError, OSError):
                        pass
                self.log(f"Konfiguration {txn} fehlgeschlagen; Rückkehr angefordert: {exc}", "error")
            self.dirty = True
            return change

    async def start_test(self, plan):
        if self.operation.locked() or self.active:
            raise ValueError("Es läuft bereits ein Versuch oder eine Konfigurationsänderung")
        async with self.operation:
            self.require_nodes([plan.source, plan.destination])
            if self.nodes[plan.source].get("peer_id") != plan.destination:
                raise ValueError("Diese direkte Verbindung ist nicht freigegeben")
            if self.nodes[plan.destination].get("peer_id") != plan.source:
                raise ValueError("Gegenrichtung ist nicht freigegeben")
            # Wire test IDs are random nonzero uint32; archive IDs remain identical throughout.
            tid = secrets.randbelow(0xFFFFFFFE)+1
            while tid in self.runs or (self.data_dir/f"{tid}.json").exists():
                tid = secrets.randbelow(0xFFFFFFFE)+1
            run = dict(id=tid, plan=plan.model_dump(), started_at=utc(), state="arming",
                       mode=self.mode, nodes={str(n):{k:v for k,v in self.nodes[n].items() if k != "_seen"}
                                             for n in (plan.source,plan.destination)},
                       reports={}, samples=[], metrics=evaluate(None,None,plan.payload_bytes))
            self.runs[tid] = run
            self.active = tid
            self.dirty = True
            fields = dict(test_id=tid,source=plan.source,destination=plan.destination,
                          payload_bytes=plan.payload_bytes,rate_pps=plan.rate_pps,duration_ms=plan.duration_s*1000)
            try:
                await self.command(plan.destination, "arm", **fields)
                await self.command(plan.source, "arm", **fields)
                await self.command(plan.source, "run", test_id=tid)
                run.update(state="running", deadline=time.monotonic()+plan.duration_s+12)
                self.log(f"Versuch {tid}: {plan.source} → {plan.destination} gestartet")
            except (ValueError, ConnectionError, TimeoutError, OSError) as exc:
                for nid in (plan.source,plan.destination):
                    try:
                        await self.command(nid,"stop",test_id=tid)
                    except (ValueError, ConnectionError, TimeoutError, OSError):
                        pass
                self.finish(run,"failed",str(exc))
                raise
            return run

    async def stop_test(self, tid):
        if self.active != tid:
            raise ValueError("Versuch ist nicht aktiv")
        run = self.runs[tid]
        if run["state"] == "arming":
            raise ValueError("Startbestätigung steht noch aus")
        await self.command(run["plan"]["source"],"stop",test_id=tid)
        run.update(state="draining",deadline=time.monotonic()+12)
        self.log(f"Versuch {tid}: Stopp bestätigt, Abschlussberichte werden abgewartet")

    def finish(self, run, state, error=None):
        run.update(state=state,finished_at=utc())
        run.pop("deadline",None)
        if error:
            run["error"] = error
        if self.active == run["id"]:
            self.active = None
        self.data_dir.mkdir(parents=True,exist_ok=True)
        dest = self.data_dir / f"{run['id']}.json"
        temporary = dest.with_suffix(".tmp")
        temporary.write_text(json.dumps(run,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
        temporary.replace(dest)
        self.dirty = True

    def incomplete(self,run,error):
        run["metrics"]["loss_pct"] = None
        run["metrics"]["delivery_pct"] = None
        run["metrics"]["radar"]["loss_pct"] = None
        self.finish(run,"incomplete",error)

    async def receive(self, event):
        kind = event.get("type")
        nid = event.get("node_id")
        if kind == "ack":
            future = self.pending.get((event.get("id"),nid,event.get("op")))
            if future and not future.done():
                future.set_result(event)
        elif kind == "status":
            if not isinstance(nid,int) or not 1 <= nid <= 65535:
                return
            if event.get("chip") != "ESP32" and self.mode != "simulation":
                self.log(f"Nicht unterstütztes Chipmodell von Knoten {nid}","error")
                return
            old = self.nodes.get(nid,{})
            if old.get("boot_id") is not None and old.get("boot_id") != event.get("boot_id") and self.active:
                run=self.runs[self.active]
                if nid in (run["plan"]["source"],run["plan"]["destination"]):
                    self.incomplete(run,f"Knoten {nid} wurde während des Versuchs neu gestartet")
            self.nodes[nid] = {**old,**event,"_seen":time.monotonic(),"last_seen":utc()}
            self.dirty = True
        elif kind == "stats":
            run = self.runs.get(event.get("test_id"))
            if not run or run["id"] != self.active:
                return
            plan = run["plan"]
            if nid not in (plan["source"],plan["destination"]):
                return
            try:
                validate_report(event)
            except ValueError as exc:
                self.log(str(exc),"error")
                return
            previous = run["reports"].get(str(nid))
            if previous and (event.get("tx",0) < previous.get("tx",0) or event.get("rx_unique",0) < previous.get("rx_unique",0)):
                self.log(f"Rückläufige Zähler von Knoten {nid}; Bericht ignoriert", "error")
                return
            run["reports"][str(nid)] = event
            sender = run["reports"].get(str(plan["source"]))
            receiver = run["reports"].get(str(plan["destination"]))
            final = bool(sender and receiver and sender.get("done") and receiver.get("done"))
            metrics = evaluate(sender,receiver,plan["payload_bytes"],final)
            run["metrics"] = metrics
            # Keep one sample per pair of fresh device reports. Final pairs always replace live values.
            if sender and receiver:
                pair = (sender.get("elapsed_ms"),receiver.get("elapsed_ms"),final)
                if run.get("_pair") != list(pair):
                    sample = dict(at=utc(),**metrics)
                    if run["samples"] and run["samples"][-1]["elapsed_s"] == metrics["elapsed_s"]:
                        run["samples"][-1] = sample
                    else:
                        run["samples"].append(sample)
                    run["samples"] = run["samples"][-250:]
                    run["_pair"] = list(pair)
            if final:
                self.finish(run,"complete" if metrics["consistency"] != "inconsistent" else "invalid")
                self.log(f"Versuch {run['id']} abgeschlossen")
            self.dirty = True
        elif kind == "warning":
            self.log(f"Knoten {nid}: {event.get('message','Warnung')}","error")

    async def tick(self):
        while True:
            if self.active:
                run = self.runs[self.active]
                if time.monotonic() > run.get("deadline",float("inf")):
                    self.incomplete(run,"Abschlussbericht fehlt; Paketverlust bleibt unbestätigt")
            # Status aging must also reach the browser while no serial messages arrive.
            payload = {"type":"state","data":self.snapshot()}
            for client in list(self.clients):
                if client.full():
                    client.get_nowait()
                client.put_nowait(payload)
            self.dirty = False
            await asyncio.sleep(.5)
