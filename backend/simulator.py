"""Explicit synthetic transport, sharing the real command and telemetry contract."""
import asyncio
import math
import time


class Simulator:
    def __init__(self, receive, disconnected=None):
        self.receive = receive
        self.nodes = {i: dict(node_id=i, role="master" if i == 1 else "slave",
                             mac=f"02:00:00:00:00:{i:02X}", chip="ESP32 (SIMULATION)",
                             idf="v6.0.1", power_qdbm=72, profile="ofdm6", channel=6,
                             bandwidth_mhz=20, peer_id=3-i, link_healthy=True,
                             powers_qdbm=[8,20,28,34,44,52,56,60,66,72,80],
                             profiles=["ofdm6","ofdm12","ofdm24","ofdm54","ht_mcs0","ht_mcs7"],
                             tx_total=0, rx_total=0, boot_id=i) for i in (1, 2)}
        self.task = None
        self.plan = None
        self.start_time = None
        self.stop_elapsed = None
        self.backups = {}
        self.report_index = 0
        self.baseline = {}

    async def start(self):
        self.task = asyncio.create_task(self.loop())

    async def send(self, cmd):
        node = self.nodes[cmd["node_id"]]
        op = cmd["op"]
        ok = True
        if op == "configure":
            self.backups.setdefault(cmd["id"], {})[node["node_id"]] = dict(node)
            node.update(power_qdbm=cmd["power_qdbm"], profile=cmd["profile"])
        elif op == "rollback":
            old = self.backups.get(cmd.get("transaction"), {}).get(node["node_id"])
            if old:
                node.update(old)
        elif op == "arm":
            if not self.plan or self.plan["test_id"] != cmd["test_id"]:
                self.plan = dict(cmd)
                self.start_time = None
                self.stop_elapsed = None
                self.report_index = 0
                self.baseline = {i:(n["tx_total"],n["rx_total"]) for i,n in self.nodes.items()}
        elif op == "run":
            if self.start_time is None:
                self.start_time = time.monotonic()
        elif op == "stop" and self.start_time:
            self.stop_elapsed = min(time.monotonic()-self.start_time, self.plan["duration_ms"]/1000)
        await self.receive({"v":1,"type":"ack","id":cmd["id"],"node_id":cmd["node_id"],"ok":ok,"op":op})

    async def loop(self):
        while True:
            for node in self.nodes.values():
                await self.receive({"v":1,"type":"status",**node})
            if self.plan and self.start_time is not None:
                raw_elapsed = time.monotonic() - self.start_time
                duration = self.stop_elapsed if self.stop_elapsed is not None else self.plan["duration_ms"]/1000
                elapsed = min(duration, raw_elapsed)
                tx = int(elapsed*self.plan["rate_pps"])
                source, dest = self.plan["source"], self.plan["destination"]
                power = self.nodes[source]["power_qdbm"]/4
                loss = min(.6, max(.01, (18-power)*.015))
                rx = tx - int(tx*loss)
                n = rx // 10
                rtt_us = 7000 + int(1000*math.sin(self.report_index/3))
                done = raw_elapsed >= duration + 1.5
                common = dict(v=1,type="stats",test_id=self.plan["test_id"],elapsed_ms=int(elapsed*1000),
                              done=done,duplicates=0,late=0,queue_drops=0,send_errors=0)
                self.nodes[source]["tx_total"] = self.baseline[source][0]+tx
                self.nodes[dest]["rx_total"] = self.baseline[dest][1]+rx
                await self.receive({**common,"node_id":source,"tx":tx,"rx_unique":0,"mac_ok":rx,
                                    "mac_fail":tx-rx,"app_acks":n,"rtt_count":n,"rtt_sum_us":n*rtt_us,
                                    "jitter_sum_us":max(0,n-1)*600,"rssi_count":0,"rssi_sum":0})
                await self.receive({**common,"node_id":dest,"tx":0,"rx_unique":rx,"mac_ok":0,"mac_fail":0,
                                    "app_acks":0,"rtt_count":0,"rtt_sum_us":0,"jitter_sum_us":0,
                                    "rssi_count":rx,"rssi_sum":rx*(-45-(18-power)*1.8)})
                self.report_index += 1
                if done:
                    self.plan = None
            await asyncio.sleep(1)

    async def close(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
