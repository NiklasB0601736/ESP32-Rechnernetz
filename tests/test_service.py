import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.models import Configuration, TestPlan
from backend.service import Lab


class FakeTransport:
    def __init__(self,lab,fail_op=None):
        self.lab=lab
        self.fail_op=fail_op
        self.sent=[]

    async def send(self,message):
        self.sent.append(message)
        if message["op"]=="configure":
            n=self.lab.nodes[message["node_id"]]
            n.update(power_qdbm=message["power_qdbm"],profile=message["profile"],_seen=time.monotonic()+2)
        await self.lab.receive(dict(v=1,type="ack",node_id=message["node_id"],id=message["id"],
                                    op=message["op"],ok=message["op"]!=self.fail_op,error="Injected failure"))


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.lab=Lab(Path(self.tmp.name))
        self.lab.mode="hardware"
        for nid in (1,2):
            await self.lab.receive(dict(v=1,type="status",node_id=nid,chip="ESP32",idf="v6.0.1",
                                        peer_id=3-nid,power_qdbm=72,profile="ofdm6",link_healthy=True,
                                        powers_qdbm=[8,44,72],profiles=["ofdm6","ofdm12"]))
        self.transport=FakeTransport(self.lab)
        self.lab.transport=self.transport

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def test_configuration_commit_and_independent_power(self):
        result=await self.lab.configure(Configuration(powers={"2":44}))
        self.assertEqual(result["state"],"success")
        self.assertEqual(self.lab.nodes[1]["power_qdbm"],72)
        self.assertEqual(self.lab.nodes[2]["power_qdbm"],44)
        self.assertEqual([c["op"] for c in self.transport.sent],["configure","commit"])

    async def test_failed_group_configuration_rolls_back_all_targets(self):
        self.transport.fail_op="commit"
        result=await self.lab.configure(Configuration(profile="ofdm12"))
        self.assertEqual(result["state"],"failed")
        rollbacks=[c["node_id"] for c in self.transport.sent if c["op"]=="rollback"]
        self.assertEqual(set(rollbacks),{1,2})

    async def test_unsupported_power_and_profile_are_never_sent(self):
        for request in [Configuration(powers={"1":77}),Configuration(profile="invented"),Configuration(powers={"9":44})]:
            with self.assertRaises(ValueError):
                await self.lab.configure(request)
        self.assertEqual(self.transport.sent,[])

    async def test_common_profiles_are_intersection_and_offline_prevents_apply(self):
        self.lab.nodes[2]["profiles"]=["ofdm6"]
        self.assertEqual([p["id"] for p in self.lab.snapshot()["profiles"]],["ofdm6"])
        self.lab.nodes[2]["_seen"]-=5
        with self.assertRaises(ValueError):
            await self.lab.configure(Configuration(profile="ofdm6"))

    async def test_receiver_is_armed_before_sender_runs(self):
        run=await self.lab.start_test(TestPlan(source=2,destination=1))
        self.assertEqual([(c["node_id"],c["op"]) for c in self.transport.sent],[(1,"arm"),(2,"arm"),(2,"run")])
        self.assertEqual(run["state"],"running")
        with self.assertRaises(ValueError):
            await self.lab.start_test(TestPlan(source=1,destination=2))

    async def test_two_final_reports_required_and_archive_is_exportable(self):
        run=await self.lab.start_test(TestPlan(source=1,destination=2,payload_bytes=100))
        def report(nid,**kw):
            return dict(v=1,type="stats",node_id=nid,test_id=run["id"],elapsed_ms=2000,
                        done=True,rtt_count=0,app_acks=0,**kw)
        await self.lab.receive(report(1,tx=100))
        self.assertEqual(self.lab.active,run["id"])
        await self.lab.receive(report(2,rx_unique=90))
        self.assertIsNone(self.lab.active)
        self.assertEqual(run["state"],"complete")
        self.assertEqual(run["metrics"]["loss_pct"],10)
        archived=json.loads((Path(self.tmp.name)/f"{run['id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(archived["metrics"]["goodput_bps"],36000)

    async def test_duplicate_and_foreign_telemetry_do_not_increment_counts(self):
        run=await self.lab.start_test(TestPlan(source=1,destination=2))
        event=dict(v=1,type="stats",node_id=1,test_id=run["id"],elapsed_ms=1000,tx=10)
        await self.lab.receive(event)
        await self.lab.receive(event)
        await self.lab.receive({**event,"node_id":9,"tx":999})
        await self.lab.receive({**event,"tx":1})
        self.assertEqual(run["reports"]["1"]["tx"],10)
        self.assertNotIn("9",run["reports"])

    async def test_unapproved_edges_cannot_start(self):
        self.lab.nodes[1]["peer_id"]=3
        with self.assertRaises(ValueError):
            await self.lab.start_test(TestPlan(source=1,destination=2))

    async def test_reboot_does_not_mix_counter_epochs(self):
        self.lab.nodes[1]["boot_id"]=100
        run=await self.lab.start_test(TestPlan(source=1,destination=2))
        await self.lab.receive(dict(v=1,type="status",node_id=1,chip="ESP32",boot_id=101))
        self.assertEqual(run["state"],"incomplete")
        self.assertIsNone(run["metrics"]["loss_pct"])
        self.assertIsNone(self.lab.active)


class SimulatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_command_path_runs_both_directions_and_stop(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            lab=Lab(Path(tmp))
            await lab.start(demo=True)
            try:
                await asyncio.sleep(.05)
                self.assertEqual(len(lab.nodes),2)
                self.assertEqual(lab.mode,"simulation")
                change=await lab.configure(Configuration(powers={"1":44},profile="ofdm12"))
                self.assertEqual(change["state"],"success")
                for source,destination in [(1,2),(2,1)]:
                    run=await lab.start_test(TestPlan(source=source,destination=destination,duration_s=1))
                    deadline=time.monotonic()+6
                    while lab.active and time.monotonic()<deadline:
                        await asyncio.sleep(.1)
                    self.assertEqual(run["state"],"complete")
                    self.assertIsNotNone(run["metrics"]["loss_pct"])
                    self.assertIsNone(run["metrics"]["ber"])
                run=await lab.start_test(TestPlan(source=1,destination=2,duration_s=20))
                await asyncio.sleep(.1)
                await lab.stop_test(run["id"])
                self.assertEqual(run["state"],"draining")
                deadline=time.monotonic()+6
                while lab.active and time.monotonic()<deadline:
                    await asyncio.sleep(.1)
                self.assertEqual(run["state"],"complete")
                self.assertLess(run["metrics"]["elapsed_s"],2)
            finally:
                await lab.close()
