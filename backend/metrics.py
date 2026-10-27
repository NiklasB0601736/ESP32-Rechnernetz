"""Pure evaluation. Missing target telemetry is never interpreted as packet loss."""
import math


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def radar(metrics):
    def score(key, transform):
        value = metrics.get(key)
        return round(max(0.0, min(100.0, transform(value))), 2) if finite(value) else None

    return {
        "ber": None,
        "loss_pct": score("loss_pct", lambda x: 100 - x),
        "goodput_bps": score("goodput_bps", lambda x: x / 100000 * 100),
        "rtt_ms": score("rtt_ms", lambda x: (1 - x / 100) * 100),
        "jitter_ms": score("jitter_ms", lambda x: (1 - x / 20) * 100),
        "rssi_dbm": score("rssi_dbm", lambda x: (x + 100) / 60 * 100),
    }


def evaluate(sender, receiver, payload_bytes, final=False):
    result = dict(ber=None, goodput_bps=None, delivery_pct=None, loss_pct=None,
                  rtt_ms=None, jitter_ms=None, rssi_dbm=None, elapsed_s=None,
                  provisional=not final, consistency="waiting")
    if sender:
        n = sender.get("rtt_count", 0)
        if n:
            result["rtt_ms"] = sender["rtt_sum_us"] / n / 1000
        if n > 1:
            result["jitter_ms"] = sender["jitter_sum_us"] / (n - 1) / 1000
    # Goodput uses the sender's duration, not the serial arrival time or the drain period.
    if sender and receiver:
        elapsed = sender.get("elapsed_ms", 0) / 1000
        tx, rx = sender.get("tx", 0), receiver.get("rx_unique", 0)
        result["elapsed_s"] = elapsed
        if elapsed > 0:
            result["goodput_bps"] = rx * payload_bytes * 8 / elapsed
        if tx >= rx and tx > 0:
            result["delivery_pct"] = rx / tx * 100
            result["loss_pct"] = (tx - rx) / tx * 100
            result["consistency"] = "final" if final else "provisional"
        elif rx > tx:
            result["goodput_bps"] = None
            result["consistency"] = "inconsistent" if final else "unaligned_snapshots"
        else:
            result["consistency"] = "no_packets"
        if receiver.get("rssi_count", 0):
            result["rssi_dbm"] = receiver["rssi_sum"] / receiver["rssi_count"]
    result["radar"] = radar(result)
    return result


def validate_report(report):
    counts = ("tx", "rx_unique", "duplicates", "late", "mac_ok", "mac_fail",
              "send_errors", "app_acks", "rtt_count", "rtt_sum_us", "jitter_sum_us",
              "rssi_count", "elapsed_ms", "queue_drops")
    for key in counts:
        if key in report and (not finite(report[key]) or report[key] < 0 or report[key] != int(report[key])):
            raise ValueError(f"Ungültiger Zähler: {key}")
    if not finite(report.get("rssi_sum", 0)):
        raise ValueError("Ungültige RSSI-Summe")
    if report.get("rtt_count", 0) > report.get("app_acks", 0):
        raise ValueError("RTT-Zähler übersteigt Anwendungsantworten")
    if report.get("tx",0)>60000 or report.get("rx_unique",0)>60000:
        raise ValueError("Zähler übersteigt Sequenzbereich")
    if report.get("mac_ok",0)+report.get("mac_fail",0)>report.get("tx",0):
        raise ValueError("MAC-Zähler übersteigen Test-TX")
