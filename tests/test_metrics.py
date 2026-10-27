import unittest

from backend.metrics import evaluate, radar, validate_report
from backend.models import TestPlan


class MetricsTests(unittest.TestCase):
    def test_known_delivery_goodput_rtt_and_jitter(self):
        sender = dict(tx=100,elapsed_ms=2000,app_acks=3,rtt_count=3,
                      rtt_sum_us=30000,jitter_sum_us=8000)
        receiver = dict(rx_unique=80,rssi_count=80,rssi_sum=-4800)
        m = evaluate(sender,receiver,100,True)
        self.assertEqual(m["goodput_bps"],32000)
        self.assertEqual(m["delivery_pct"],80)
        self.assertEqual(m["loss_pct"],20)
        self.assertEqual(m["rtt_ms"],10)
        self.assertEqual(m["jitter_ms"],4)
        self.assertEqual(m["rssi_dbm"],-60)
        self.assertIsNone(m["ber"])

    def test_missing_receiver_does_not_prove_forward_loss(self):
        m = evaluate(dict(tx=100,elapsed_ms=1000,app_acks=0),None,128,True)
        self.assertIsNone(m["loss_pct"])
        self.assertIsNone(m["goodput_bps"])
        self.assertIsNone(m["radar"]["loss_pct"])

    def test_zero_target_receptions_is_real_total_loss(self):
        m = evaluate(dict(tx=100,elapsed_ms=1000),dict(rx_unique=0),128,True)
        self.assertEqual(m["loss_pct"],100)
        self.assertEqual(m["goodput_bps"],0)
        self.assertIsNone(m["rssi_dbm"])
        self.assertIsNone(m["rtt_ms"])

    def test_missing_ack_does_not_change_packet_delivery(self):
        m = evaluate(dict(tx=100,elapsed_ms=1000,app_acks=0),dict(rx_unique=100),128,True)
        self.assertEqual(m["loss_pct"],0)
        self.assertIsNone(m["rtt_ms"])

    def test_temporarily_misaligned_reports_do_not_create_negative_loss(self):
        m = evaluate(dict(tx=10,elapsed_ms=1000),dict(rx_unique=12),128)
        self.assertIsNone(m["loss_pct"])
        self.assertIsNone(m["goodput_bps"])
        self.assertEqual(m["consistency"],"unaligned_snapshots")
        m = evaluate(dict(tx=10,elapsed_ms=1000),dict(rx_unique=12),128,True)
        self.assertEqual(m["consistency"],"inconsistent")

    def test_empty_window_and_single_rtt_have_no_fake_values(self):
        m = evaluate(dict(tx=0,elapsed_ms=0,rtt_count=1,rtt_sum_us=12000),dict(rx_unique=0),128)
        self.assertIsNone(m["loss_pct"])
        self.assertIsNone(m["goodput_bps"])
        self.assertIsNone(m["jitter_ms"])
        self.assertEqual(m["rtt_ms"],12)

    def test_radar_reference_endpoints_clamp_and_missing(self):
        self.assertTrue(all(v is None for v in radar({}).values()))
        best = radar(dict(loss_pct=0,goodput_bps=100000,rtt_ms=0,jitter_ms=0,rssi_dbm=-40))
        self.assertTrue(all(v==100 for k,v in best.items() if k!="ber"))
        worst = radar(dict(loss_pct=100,goodput_bps=0,rtt_ms=100,jitter_ms=20,rssi_dbm=-100))
        self.assertTrue(all(v==0 for k,v in worst.items() if k!="ber"))
        self.assertEqual(radar(dict(rssi_dbm=-70))["rssi_dbm"],50)
        self.assertEqual(radar(dict(goodput_bps=999999))["goodput_bps"],100)
        self.assertIsNone(radar(dict(rtt_ms=float("nan")))["rtt_ms"])

    def test_invalid_counters_are_rejected(self):
        for report in [dict(tx=-1),dict(rx_unique=float("inf")),dict(rtt_count=3,app_acks=2),
                       dict(rx_unique=60001),dict(tx=1.5),dict(tx=10,mac_ok=11)]:
            with self.assertRaises(ValueError):
                validate_report(report)

    def test_wire_limits_and_distinct_nodes(self):
        for plan in [dict(source=1,destination=1),dict(source=1,destination=2,payload_bytes=219),
                     dict(source=1,destination=2,rate_pps=501)]:
            with self.assertRaises(ValueError):
                TestPlan(**plan)
