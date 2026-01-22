from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Awaitable

from .const import BUCKET_SECONDS
from .storage import CurveState


def _parse_power_w(state_str: str | None) -> float | None:
    if state_str is None:
        return None
    if state_str in ("unknown", "unavailable"):
        return None
    try:
        return float(state_str)
    except ValueError:
        return None


def _add_energy_slice_to_buckets(
    run_start: datetime,
    buckets_kwh: list[float],
    t0: datetime,
    t1: datetime,
    power_w: float,
) -> None:
    if t1 <= t0:
        return

    cur = t0
    while cur < t1:
        seconds_from_start = (cur - run_start).total_seconds()
        bucket_index = int(seconds_from_start // BUCKET_SECONDS)

        bucket_end = run_start + timedelta(seconds=(bucket_index + 1) * BUCKET_SECONDS)
        seg_end = bucket_end if bucket_end < t1 else t1

        seg_seconds = (seg_end - cur).total_seconds()
        seg_kwh = power_w * seg_seconds / 3_600_000.0

        while len(buckets_kwh) <= bucket_index:
            buckets_kwh.append(0.0)

        buckets_kwh[bucket_index] += seg_kwh
        cur = seg_end


def _iso_now_local(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone().isoformat(timespec="seconds")


@dataclass
class RunState:
    in_run: bool = False
    run_start_ts: datetime | None = None
    below_standby_since: datetime | None = None
    current_run_buckets_kwh: list[float] = None  # type: ignore


class CurveTracker:
    def __init__(
        self,
        standby_w: float,
        wait_time_s: int,
        expected_runtime_s: int,
        schedule_call_later,
        on_state_updated: Callable[[], None],
        on_persist_requested: Callable[[], Awaitable[None]],
    ) -> None:
        self.standby_w = float(standby_w)
        self.wait_time_s = int(wait_time_s)

        self._on_state_updated = on_state_updated
        self._on_persist_requested = on_persist_requested

        self.curve_state: CurveState = CurveState.empty()
        self.run = RunState(in_run=False, run_start_ts=None, below_standby_since=None, current_run_buckets_kwh=[])

        self.last_ts: datetime | None = None
        self.last_power_w: float | None = None

        self.expected_runtime_s = int(expected_runtime_s)
        self._schedule_call_later = schedule_call_later
        self._cutoff_unsub = None

    async def _hard_cutoff(self) -> None:
        if not self.run.in_run or self.run.run_start_ts is None:
            return

        cutoff_ts = self.run.run_start_ts + timedelta(seconds=self.expected_runtime_s)

        if self.last_ts is not None and self.last_power_w is not None:
            if cutoff_ts > self.last_ts:
                _add_energy_slice_to_buckets(
                    self.run.run_start_ts,
                    self.run.current_run_buckets_kwh,
                    self.last_ts,
                    cutoff_ts,
                    self.last_power_w,
                )

        self.last_ts = cutoff_ts
        await self.finish_run(cutoff_ts)

    async def load_state(self, state: CurveState) -> None:
        self.curve_state = state
        self._on_state_updated()

    def _cancel_cutoff_timer(self) -> None:
        if self._cutoff_unsub is not None:
            self._cutoff_unsub()
            self._cutoff_unsub = None

    def start_run(self, now: datetime) -> None:
        self.run.in_run = True
        self.run.run_start_ts = now
        self.run.below_standby_since = None
        self.run.current_run_buckets_kwh = []
        self._cancel_cutoff_timer()

        if self.expected_runtime_s > 0:
            async def _cutoff(_):
                await self._hard_cutoff()
            self._cutoff_unsub = self._schedule_call_later(self.expected_runtime_s, _cutoff)

        self._on_state_updated()

    def mark_below_standby(self, now: datetime) -> None:
        if self.run.below_standby_since is None:
            self.run.below_standby_since = now

    def clear_below_standby(self) -> None:
        self.run.below_standby_since = None

    def below_standby_long_enough(self, now: datetime) -> bool:
        if self.run.below_standby_since is None:
            return False
        return (now - self.run.below_standby_since).total_seconds() >= self.wait_time_s

    async def finish_run(self, now: datetime) -> None:
        self._cancel_cutoff_timer()
        self.run.in_run = False

        last_run = list(self.run.current_run_buckets_kwh)
        total_kwh = float(sum(last_run))

        duration_minutes = 0
        if self.run.run_start_ts is not None:
            duration_minutes = int((now - self.run.run_start_ts).total_seconds() // 60)

        self._update_running_mean(last_run)

        self.curve_state.last_run_kwh_per_interval = last_run
        self.curve_state.last_run_total_kwh = total_kwh
        self.curve_state.last_run_duration_minutes = duration_minutes
        self.curve_state.last_updated_iso = _iso_now_local(now)

        self._on_state_updated()
        await self._on_persist_requested()

        self.run.run_start_ts = None
        self.run.below_standby_since = None
        self.run.current_run_buckets_kwh = []

    def _update_running_mean(self, new_run: list[float]) -> None:
        mean = self.curve_state.mean_kwh_per_interval
        counts = self.curve_state.bucket_counts

        if len(mean) < len(new_run):
            mean.extend([0.0] * (len(new_run) - len(mean)))
        if len(counts) < len(new_run):
            counts.extend([0] * (len(new_run) - len(counts)))

        for i, val in enumerate(new_run):
            counts[i] += 1
            c = counts[i]
            mean[i] = mean[i] + (val - mean[i]) / c

        self.curve_state.runs += 1
        self.curve_state.mean_kwh_per_interval = mean
        self.curve_state.bucket_counts = counts

    async def handle_power_change(self, old_state_str: str | None, new_state_str: str | None, now: datetime) -> None:
        new_w = _parse_power_w(new_state_str)

        if self.last_ts is not None and self.last_power_w is not None:
            if self.run.in_run and self.run.run_start_ts is not None:
                _add_energy_slice_to_buckets(
                    self.run.run_start_ts,
                    self.run.current_run_buckets_kwh,
                    self.last_ts,
                    now,
                    self.last_power_w,
                )

        self.last_ts = now
        self.last_power_w = new_w

        if new_w is None:
            return

        if not self.run.in_run:
            if new_w > self.standby_w:
                self.start_run(now)
            return

        if new_w < self.standby_w:
            self.mark_below_standby(now)
            if self.below_standby_long_enough(now):
                await self.finish_run(now)
        else:
            self.clear_below_standby()
