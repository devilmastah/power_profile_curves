from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_call_later
from homeassistant.components.sensor import SensorEntity

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_POWER_ENTITY,
    CONF_STANDBY_W,
    CONF_WAIT_TIME_S,
    CONF_EXPECTED_RUNTIME_S,
    CONF_PRICE_ENTITY,
    BUCKET_MINUTES,
)
from .curve_tracker import CurveTracker
from .storage import CurveStorage
from .price_calc import parse_tibber_prices_attributes, compute_start_costs_quarters, best_start, PriceTimeline


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    name = entry.data.get(CONF_NAME) or entry.title
    power_entity = entry.data[CONF_POWER_ENTITY]
    standby_w = float(entry.data[CONF_STANDBY_W])
    wait_time_s = int(entry.data[CONF_WAIT_TIME_S])
    expected_runtime_s = int(entry.data.get(CONF_EXPECTED_RUNTIME_S, 0))
    price_entity = entry.data.get(CONF_PRICE_ENTITY)

    storage = CurveStorage(hass, entry.entry_id)

    sensor = PowerCurveSensor(
        hass=hass,
        entry=entry,
        name=name,
        power_entity=power_entity,
        standby_w=standby_w,
        wait_time_s=wait_time_s,
        expected_runtime_s=expected_runtime_s,
        price_entity=price_entity,
        storage=storage,
    )

    async_add_entities([sensor], update_before_add=True)
    await sensor.async_start_listening()


class PowerCurveSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        name: str,
        power_entity: str,
        standby_w: float,
        wait_time_s: int,
        expected_runtime_s: int,
        price_entity: str | None,
        storage: CurveStorage,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self._storage = storage

        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}:{entry.entry_id}"
        self._attr_icon = "mdi:chart-line"

        self._expected_runtime_s = expected_runtime_s
        self._power_entity = power_entity
        self._standby_w = standby_w
        self._wait_time_s = wait_time_s
        self._price_entity = price_entity

        self._unsub_power = None
        self._unsub_price = None

        self._price_timeline: PriceTimeline | None = None
        self._start_cost_today: list[float | None] | None = None
        self._start_cost_tomorrow: list[float | None] | None = None
        self._best_today: tuple[int | None, float | None] = (None, None)
        self._best_tomorrow: tuple[int | None, float | None] = (None, None)

        @callback
        def _on_state_updated() -> None:
            # curve updated, recompute costs then update state
            self.hass.async_create_task(self._async_recompute_costs())
            self.async_write_ha_state()

        async def _persist() -> None:
            await self._storage.save(self._tracker.curve_state)

        def _schedule_call_later(delay_s: int, async_cb):
            return async_call_later(self.hass, delay_s, async_cb)

        self._tracker = CurveTracker(
            standby_w=standby_w,
            wait_time_s=wait_time_s,
            expected_runtime_s=expected_runtime_s,
            schedule_call_later=_schedule_call_later,
            on_state_updated=_on_state_updated,
            on_persist_requested=_persist,
        )

    async def async_added_to_hass(self) -> None:
        loaded = await self._storage.load()
        await self._tracker.load_state(loaded)

        # Load initial price timeline, if configured
        await self._async_refresh_price_timeline_from_state()
        await self._async_recompute_costs()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_power is not None:
            self._unsub_power()
            self._unsub_power = None
        if self._unsub_price is not None:
            self._unsub_price()
            self._unsub_price = None

    async def async_start_listening(self) -> None:
        if self._unsub_power is not None:
            return

        async def _handle_power(event) -> None:
            old = event.data.get("old_state")
            new = event.data.get("new_state")
            if new is None:
                return
            now: datetime = new.last_updated
            old_str = old.state if old is not None else None
            new_str = new.state
            await self._tracker.handle_power_change(old_str, new_str, now)

        self._unsub_power = async_track_state_change_event(
            self.hass,
            [self._power_entity],
            _handle_power,
        )

        if self._price_entity:
            async def _handle_price(event) -> None:
                await self._async_refresh_price_timeline_from_event(event)
                await self._async_recompute_costs()
                self.async_write_ha_state()

            self._unsub_price = async_track_state_change_event(
                self.hass,
                [self._price_entity],
                _handle_price,
            )

    async def _async_refresh_price_timeline_from_state(self) -> None:
        if not self._price_entity:
            self._price_timeline = None
            return
        st = self.hass.states.get(self._price_entity)
        if st is None:
            self._price_timeline = None
            return
        tl = parse_tibber_prices_attributes(dict(st.attributes))
        self._price_timeline = tl

    async def _async_refresh_price_timeline_from_event(self, event) -> None:
        if not self._price_entity:
            self._price_timeline = None
            return
        new = event.data.get("new_state")
        if new is None:
            self._price_timeline = None
            return
        tl = parse_tibber_prices_attributes(dict(new.attributes))
        self._price_timeline = tl

    async def _async_recompute_costs(self) -> None:
        if not self._price_timeline:
            self._start_cost_today = None
            self._start_cost_tomorrow = None
            self._best_today = (None, None)
            self._best_tomorrow = (None, None)
            return

        curve = list(self._tracker.curve_state.mean_kwh_per_interval)
        all_quarters = self._price_timeline.all_quarters

        self._start_cost_today = compute_start_costs_quarters(
            device_kwh_5m=curve,
            all_price_quarters=all_quarters,
            start_offset_quarters=0,
            start_count=96,
        )
        self._start_cost_tomorrow = compute_start_costs_quarters(
            device_kwh_5m=curve,
            all_price_quarters=all_quarters,
            start_offset_quarters=96,
            start_count=96,
        )

        self._best_today = best_start(self._start_cost_today)
        self._best_tomorrow = best_start(self._start_cost_tomorrow)

    @property
    def native_value(self) -> Any:
        return self._tracker.curve_state.runs

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self._tracker.curve_state

        mean_raw = state.mean_kwh_per_interval
        last_raw = state.last_run_kwh_per_interval

        mean_4dp = [round(v, 4) for v in mean_raw]
        last_4dp = [round(v, 4) for v in last_raw]

        price_res = None
        if self._price_timeline:
            price_res = self._price_timeline.resolution_minutes

        def round_costs(vals: list[float | None] | None, dp: int) -> list[float | None] | None:
            if vals is None:
                return None
            out: list[float | None] = []
            for v in vals:
                out.append(None if v is None else round(v, dp))
            return out

        best_today_i, best_today_cost = self._best_today
        best_tomorrow_i, best_tomorrow_cost = self._best_tomorrow

        return {
            "version": 2,
            "interval_minutes": BUCKET_MINUTES,

            "power_entity": self._power_entity,
            "standby_w": self._standby_w,
            "wait_time_s": self._wait_time_s,
            "expected_runtime_s": self._expected_runtime_s,

            "runs": state.runs,

            # Curve
            "mean_kwh_per_interval": mean_raw,
            "mean_kwh_per_interval_4dp": mean_4dp,
            "last_run_kwh_per_interval": last_raw,
            "last_run_kwh_per_interval_4dp": last_4dp,
            "bucket_counts": state.bucket_counts,
            "last_run_total_kwh": round(state.last_run_total_kwh, 4),
            "last_run_duration_minutes": state.last_run_duration_minutes,
            "last_updated": state.last_updated_iso,

            # Prices and computed start costs
            "price_entity": self._price_entity,
            "price_resolution_minutes": price_res,

            "start_cost_today": self._start_cost_today,
            "start_cost_tomorrow": self._start_cost_tomorrow,

            "start_cost_today_4dp": round_costs(self._start_cost_today, 4),
            "start_cost_tomorrow_4dp": round_costs(self._start_cost_tomorrow, 4),

            "best_start_today_quarter_index": best_today_i,
            "best_start_today_cost": None if best_today_cost is None else round(best_today_cost, 4),

            "best_start_tomorrow_quarter_index": best_tomorrow_i,
            "best_start_tomorrow_cost": None if best_tomorrow_cost is None else round(best_tomorrow_cost, 4),
        }
