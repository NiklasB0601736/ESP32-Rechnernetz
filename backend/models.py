from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ConnectRequest(Request):
    port: str = Field(min_length=1, max_length=100)


class Configuration(Request):
    powers: dict[str, int] = Field(default_factory=dict)  # node ID keys; quarter dBm
    profile: str | None = None


class TestPlan(Request):
    source: int = Field(ge=1, le=65535)
    destination: int = Field(ge=1, le=65535)
    payload_bytes: int = Field(default=128, ge=1, le=218)
    rate_pps: int = Field(default=50, ge=1, le=500)
    duration_s: int = Field(default=20, ge=1, le=120)

    @model_validator(mode="after")
    def different_nodes(self):
        if self.source == self.destination:
            raise ValueError("Sender und Empfänger müssen verschieden sein")
        if self.rate_pps * self.duration_s > 60000:
            raise ValueError("Höchstens 60000 Testpakete pro Versuch")
        return self


PROFILES = {
    "ofdm6": {"label": "OFDM · BPSK · 1/2 · 6 Mbit/s", "mbps": 6},
    "ofdm12": {"label": "OFDM · QPSK · 1/2 · 12 Mbit/s", "mbps": 12},
    "ofdm24": {"label": "OFDM · 16-QAM · 1/2 · 24 Mbit/s", "mbps": 24},
    "ofdm54": {"label": "OFDM · 64-QAM · 3/4 · 54 Mbit/s", "mbps": 54},
    "ht_mcs0": {"label": "HT20 MCS0 · BPSK · 1/2 · 6,5 Mbit/s · GI 800 ns", "mbps": 6.5},
    "ht_mcs7": {"label": "HT20 MCS7 · 64-QAM · 5/6 · 65 Mbit/s · GI 800 ns", "mbps": 65},
}
