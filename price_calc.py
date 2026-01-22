from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class PriceTimeline:
    today_quarters: list[float]
    tomorrow_quarters: list[float]
    all_quarters: list[float]
    resolution_minutes: int


def _parse_iso(ts: str) -> datetime | None:
    try:
        # accepts 2026-01-22T00:00:00.000+01:00
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _infer_resolution_minutes(entries: list[dict[str, Any]]) -> int:
    if len(entries) < 2:
        return 60
    t0 = _parse_iso(str(entries[0].get("startsAt", "")))
    t1 = _parse_iso(str(entries[1].get("startsAt", "")))
    if t0 is None or t1 is None:
        return 60
    delta_s = int((t1 - t0).total_seconds())
    if delta_s <= 0:
        return 60
    if delta_s <= 900:
        return 15
    return 60


def _expand_to_quarters(values: list[float], resolution_minutes: int) -> list[float]:
    if resolution_minutes == 15:
        return values
    if resolution_minutes == 60:
        out: list[float] = []
        for v in values:
            out.extend([v, v, v, v])
        return out
    # fallback, best effort
    factor = max(1, int(resolution_minutes / 15))
    out2: list[float] = []
    for v in values:
        for _ in range(factor):
            out2.append(v)
    return out2


def parse_tibber_prices_attributes(attrs: dict[str, Any]) -> PriceTimeline | None:
    today = attrs.get("today") or []
    tomorrow = attrs.get("tomorrow") or []

    if not isinstance(today, list):
        today = []
    if not isinstance(tomorrow, list):
        tomorrow = []

    resolution = _infer_resolution_minutes(today) if today else _infer_resolution_minutes(tomorrow)

    def extract(vals: list[dict[str, Any]]) -> list[float]:
        out: list[float] = []
        for it in vals:
            try:
                out.append(float(it.get("total")))
            except Exception:
                continue
        return out

    today_vals = extract(today)
    tomorrow_vals = extract(tomorrow)

    today_q = _expand_to_quarters(today_vals, resolution)
    tomorrow_q = _expand_to_quarters(tomorrow_vals, resolution)

    # if hourly source, we should end at 96 entries for the day
    today_q = today_q[:96]
    tomorrow_q = tomorrow_q[:96]

    all_q = list(today_q) + list(tomorrow_q)
    return PriceTimeline(
        today_quarters=today_q,
        tomorrow_quarters=tomorrow_q,
        all_quarters=all_q,
        resolution_minutes=resolution,
    )


def compute_start_costs_quarters(
    device_kwh_5m: list[float],
    all_price_quarters: list[float],
    start_offset_quarters: int,
    start_count: int = 96,
) -> list[float | None]:
    if not device_kwh_5m:
        return [0.0] * start_count

    # device bucket i maps to quarter index start + (i // 3)
    needed_quarters = (len(device_kwh_5m) + 2) // 3

    out: list[float | None] = []
    for s in range(start_count):
        base = start_offset_quarters + s
        if base < 0:
            out.append(None)
            continue
        if base + needed_quarters > len(all_price_quarters):
            out.append(None)
            continue

        cost = 0.0
        for i, kwh in enumerate(device_kwh_5m):
            q = base + (i // 3)
            cost += kwh * all_price_quarters[q]
        out.append(cost)
    return out


def best_start(costs: list[float | None]) -> tuple[int | None, float | None]:
    best_i: int | None = None
    best_c: float | None = None
    for i, c in enumerate(costs):
        if c is None:
            continue
        if best_c is None or c < best_c:
            best_c = c
            best_i = i
    return best_i, best_c
