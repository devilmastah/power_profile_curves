from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY_PREFIX, STORAGE_VERSION


@dataclass
class CurveState:
    runs: int
    mean_kwh_per_interval: list[float]
    bucket_counts: list[int]
    last_run_kwh_per_interval: list[float]
    last_run_total_kwh: float
    last_run_duration_minutes: int
    last_updated_iso: str

    @staticmethod
    def empty() -> "CurveState":
        return CurveState(
            runs=0,
            mean_kwh_per_interval=[],
            bucket_counts=[],
            last_run_kwh_per_interval=[],
            last_run_total_kwh=0.0,
            last_run_duration_minutes=0,
            last_updated_iso="",
        )

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "CurveState":
        state = CurveState.empty()
        state.runs = int(data.get("runs", 0))
        state.mean_kwh_per_interval = list(data.get("mean_kwh_per_interval", []))

        raw_counts = data.get("bucket_counts")
        if isinstance(raw_counts, list) and raw_counts:
            state.bucket_counts = [int(x) for x in raw_counts]
        else:
            state.bucket_counts = [state.runs] * len(state.mean_kwh_per_interval)

        state.last_run_kwh_per_interval = list(data.get("last_run_kwh_per_interval", []))
        state.last_run_total_kwh = float(data.get("last_run_total_kwh", 0.0))
        state.last_run_duration_minutes = int(data.get("last_run_duration_minutes", 0))
        state.last_updated_iso = str(data.get("last_updated_iso", ""))
        return state

    def to_dict(self) -> dict[str, Any]:
        return {
            "runs": self.runs,
            "mean_kwh_per_interval": self.mean_kwh_per_interval,
            "bucket_counts": self.bucket_counts,
            "last_run_kwh_per_interval": self.last_run_kwh_per_interval,
            "last_run_total_kwh": self.last_run_total_kwh,
            "last_run_duration_minutes": self.last_run_duration_minutes,
            "last_updated_iso": self.last_updated_iso,
        }


class CurveStorage:
    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        key = f"{STORAGE_KEY_PREFIX}{entry_id}"
        self._store: Store = Store(hass, STORAGE_VERSION, key)

    async def load(self) -> CurveState:
        data = await self._store.async_load()
        if not isinstance(data, dict):
            return CurveState.empty()
        return CurveState.from_dict(data)

    async def save(self, state: CurveState) -> None:
        await self._store.async_save(state.to_dict())
