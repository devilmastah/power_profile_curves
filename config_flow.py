from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_POWER_ENTITY,
    CONF_STANDBY_W,
    CONF_WAIT_TIME_S,
    CONF_EXPECTED_RUNTIME_S,
    CONF_PRICE_ENTITY,
)


class PowerCurveProfilesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            power_entity = user_input[CONF_POWER_ENTITY]
            expected_runtime_s = int(user_input.get(CONF_EXPECTED_RUNTIME_S, 0))
            price_entity = user_input.get(CONF_PRICE_ENTITY) or "none"

            await self.async_set_unique_id(f"{DOMAIN}:{power_entity}:{expected_runtime_s}:{price_entity}")
            self._abort_if_unique_id_configured()

            if expected_runtime_s > 0:
                title = user_input.get(CONF_NAME) or f"Power curve {power_entity} ({expected_runtime_s}s cutoff)"
            else:
                title = user_input.get(CONF_NAME) or f"Power curve {power_entity} (threshold stop)"

            return self.async_create_entry(title=title, data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME): TextSelector(TextSelectorConfig()),
                vol.Required(CONF_POWER_ENTITY): EntitySelector(
                    EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_STANDBY_W, default=20.0): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=10000,
                        step=0.1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="W",
                    )
                ),
                vol.Required(CONF_WAIT_TIME_S, default=300): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=7200,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Optional(CONF_EXPECTED_RUNTIME_S, default=0): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=24 * 3600,
                        step=60,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Optional(CONF_PRICE_ENTITY): EntitySelector(
                    EntitySelectorConfig(domain="sensor")
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
