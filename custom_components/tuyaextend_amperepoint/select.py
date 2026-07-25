from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MODEL, CONF_PV_MODE, CONF_SOURCE_WORK_MODE, DOMAIN
from .coordinator import AmperePointCoordinator
from .entity import AmperePointEntity, AmperePointEntityDescription
from .models import MODELS
from .surplus import MODE_OFF, SURPLUS_MODES


MODEL_DESCRIPTION = AmperePointEntityDescription(
    key="model",
    translation_key="model",
    icon="mdi:ev-plug-type2",
)

PV_MODE_DESCRIPTION = AmperePointEntityDescription(
    key="pv_mode",
    translation_key="pv_mode",
    icon="mdi:solar-power-variant",
)

CHARGING_MODE_DESCRIPTION = AmperePointEntityDescription(
    key="charging_mode",
    translation_key="charging_mode",
    icon="mdi:ev-station",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AmperePointCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SelectEntity] = [
        AmperePointModelSelect(coordinator),
        AmperePointPvModeSelect(coordinator),
    ]
    mode_source = entry.options.get(CONF_SOURCE_WORK_MODE) or entry.data.get(
        CONF_SOURCE_WORK_MODE
    )
    if (
        mode_source and mode_source.split(".", 1)[0] == "select"
    ) or coordinator.can_write_dp("work_mode"):
        entities.append(AmperePointChargingModeSelect(coordinator))
    async_add_entities(entities)


class AmperePointPvModeSelect(AmperePointEntity, SelectEntity):
    """Switch the photovoltaic surplus mode without reopening the options."""

    def __init__(self, coordinator: AmperePointCoordinator) -> None:
        super().__init__(coordinator, PV_MODE_DESCRIPTION)

    @property
    def options(self) -> list[str]:
        return list(SURPLUS_MODES.values())

    @property
    def current_option(self) -> str | None:
        mode = self.coordinator.data.get("surplus_mode", MODE_OFF)
        return SURPLUS_MODES.get(mode, SURPLUS_MODES[MODE_OFF])

    async def async_select_option(self, option: str) -> None:
        mode = next(
            (key for key, label in SURPLUS_MODES.items() if label == option),
            None,
        )
        if mode is None:
            return
        entry = self.coordinator.config_entry
        self.hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_PV_MODE: mode}
        )
        # A mode change restarts control from fresh measurements.
        self.coordinator.surplus_engine.reset()
        await self.coordinator.async_request_refresh()


class AmperePointModelSelect(AmperePointEntity, SelectEntity):
    def __init__(self, coordinator: AmperePointCoordinator) -> None:
        super().__init__(coordinator, MODEL_DESCRIPTION)

    @property
    def options(self) -> list[str]:
        return [model.name for model in MODELS.values()]

    @property
    def current_option(self) -> str | None:
        return self.coordinator.model.name

    async def async_select_option(self, option: str) -> None:
        model_key = next(
            (key for key, model in MODELS.items() if model.name == option),
            None,
        )
        if model_key is None:
            return

        entry = self.coordinator.config_entry
        data = {**entry.data, CONF_MODEL: model_key}
        self.hass.config_entries.async_update_entry(entry, data=data)
        self.coordinator.set_model(model_key)
        await self.coordinator.async_request_refresh()


class AmperePointChargingModeSelect(AmperePointEntity, SelectEntity):
    def __init__(self, coordinator: AmperePointCoordinator) -> None:
        super().__init__(coordinator, CHARGING_MODE_DESCRIPTION)

    @property
    def options(self) -> list[str]:
        source_entity = self.coordinator._config(CONF_SOURCE_WORK_MODE)
        if source_entity:
            state = self.hass.states.get(source_entity)
            if state is not None:
                return list(state.attributes.get("options", []))
        return list(self.coordinator.dp_definition("work_mode").get("range") or [])

    @property
    def current_option(self) -> str | None:
        return self.coordinator.data.get("work_mode")

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_work_mode(option)
        await self.coordinator.async_request_refresh()
