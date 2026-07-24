from __future__ import annotations

import re

from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant

from .const import CONF_SOURCE_DEVICE_ID, DOMAIN
from .discovery import discover_sources

_AUTO_ADOPTION_STARTED = "auto_adoption_started"

_ENTITY_ID_PATTERN = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")


def _used_entity_ids(hass: HomeAssistant) -> set[str]:
    """Return every entity id referenced by existing entries.

    Manually created entries store no source device id, so mapped entity ids
    are the only way to recognize that a discovered charger is already
    configured and must not be adopted a second time.
    """
    used: set[str] = set()
    for config_entry in hass.config_entries.async_entries(DOMAIN):
        for value in {**config_entry.data, **config_entry.options}.values():
            if isinstance(value, str) and _ENTITY_ID_PATTERN.match(value):
                used.add(value)
    return used


def start_auto_adoption(hass: HomeAssistant) -> int:
    """Schedule one discovery pass for unconfigured AmperePoint chargers.

    Config-entry setup runs again for every entry created by discovery.  The
    domain guard prevents those nested setups from scheduling duplicate flows
    while the first pass is still in flight.
    """
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(_AUTO_ADOPTION_STARTED):
        return 0

    if not hass.is_running:
        # Source entities are still restoring while Home Assistant starts;
        # scanning now can freeze incomplete mappings (for example a Prime
        # whose telemetry attribute is not populated yet) into new entries.
        domain_data[_AUTO_ADOPTION_STARTED] = True

        async def _scan_after_start(_event) -> None:
            domain_data[_AUTO_ADOPTION_STARTED] = False
            start_auto_adoption(hass)

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _scan_after_start)
        return 0

    candidates = discover_sources(hass)
    if not candidates:
        return 0

    domain_data[_AUTO_ADOPTION_STARTED] = True
    configured_device_ids = {
        str(config_entry.data.get(CONF_SOURCE_DEVICE_ID, ""))
        for config_entry in hass.config_entries.async_entries(DOMAIN)
    }
    used_entities = _used_entity_ids(hass)

    scheduled = 0
    for candidate in candidates:
        if candidate.device_id in configured_device_ids:
            continue
        if any(
            entity_id in used_entities for entity_id in candidate.mapping.values()
        ):
            continue
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data=candidate.as_config_data(),
            )
        )
        scheduled += 1
    return scheduled
