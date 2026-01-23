from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .storage import CurveStorage, CurveState


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([PowerCurveResetButton(hass, entry)], update_before_add=False)


class PowerCurveResetButton(ButtonEntity):
    _attr_icon = "mdi:backup-restore"
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

        self._attr_unique_id = f"{DOMAIN}:{entry.entry_id}:reset"
        self._attr_name = "Reset statistics"
        self._storage = CurveStorage(hass, entry.entry_id)

    async def async_press(self) -> None:
        # Reset stored curve state
        state = CurveState.empty()
        await self._storage.save(state)

        # If the sensor entity is loaded, reset its in-memory tracker too
        domain_data = self.hass.data.get(DOMAIN, {})
        sensor = domain_data.get(self.entry.entry_id)
        if sensor is not None:
            await sensor.async_reset_curve_state()
