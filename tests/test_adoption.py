from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import load_integration_module  # noqa: E402

adoption = load_integration_module("adoption")
const = load_integration_module("const")


class _Candidate:
    def __init__(self, device_id: str, mapping: dict[str, str] | None = None) -> None:
        self.device_id = device_id
        self.mapping = mapping or {}

    def as_config_data(self) -> dict[str, str]:
        return {const.CONF_SOURCE_DEVICE_ID: self.device_id, **self.mapping}


class _Flow:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, dict]] = []

    async def async_init(self, domain: str, *, context: dict, data: dict) -> None:
        self.calls.append((domain, context, data))


class _ConfigEntries:
    def __init__(
        self,
        configured_ids: tuple[str, ...],
        entry_data: tuple[dict, ...] = (),
    ) -> None:
        self.flow = _Flow()
        self._entries = [
            types.SimpleNamespace(
                data={const.CONF_SOURCE_DEVICE_ID: device_id}, options={}
            )
            for device_id in configured_ids
        ] + [
            types.SimpleNamespace(data=dict(data), options={})
            for data in entry_data
        ]

    def async_entries(self, domain: str):
        return list(self._entries) if domain == const.DOMAIN else []


class _Bus:
    def __init__(self) -> None:
        self.listeners: list[tuple[str, object]] = []

    def async_listen_once(self, event: str, listener) -> None:
        self.listeners.append((event, listener))


class _Hass:
    def __init__(
        self,
        configured_ids: tuple[str, ...] = (),
        entry_data: tuple[dict, ...] = (),
        is_running: bool = True,
    ) -> None:
        self.data: dict = {}
        self.config_entries = _ConfigEntries(configured_ids, entry_data)
        self.tasks = []
        self.is_running = is_running
        self.bus = _Bus()

    def async_create_task(self, coroutine) -> None:
        self.tasks.append(coroutine)

    def close_tasks(self) -> None:
        for task in self.tasks:
            task.close()


class AutoAdoptionTests(unittest.TestCase):
    def test_schedules_only_unconfigured_devices_once(self) -> None:
        hass = _Hass(("configured",))
        candidates = [_Candidate("configured"), _Candidate("new")]
        try:
            with patch.object(adoption, "discover_sources", return_value=candidates):
                self.assertEqual(adoption.start_auto_adoption(hass), 1)
                self.assertEqual(adoption.start_auto_adoption(hass), 0)

            self.assertEqual(len(hass.tasks), 1)
            self.assertTrue(hass.data[const.DOMAIN][adoption._AUTO_ADOPTION_STARTED])
        finally:
            hass.close_tasks()

    def test_empty_discovery_can_be_retried_later(self) -> None:
        hass = _Hass()
        with patch.object(adoption, "discover_sources", return_value=[]):
            self.assertEqual(adoption.start_auto_adoption(hass), 0)

        self.assertNotIn(
            adoption._AUTO_ADOPTION_STARTED, hass.data.get(const.DOMAIN, {})
        )
        try:
            with patch.object(
                adoption, "discover_sources", return_value=[_Candidate("new")]
            ):
                self.assertEqual(adoption.start_auto_adoption(hass), 1)
        finally:
            hass.close_tasks()


    def test_adoption_is_deferred_until_home_assistant_started(self) -> None:
        hass = _Hass(is_running=False)
        with patch.object(
            adoption, "discover_sources", return_value=[_Candidate("new")]
        ) as discover:
            self.assertEqual(adoption.start_auto_adoption(hass), 0)
            discover.assert_not_called()

        self.assertEqual(len(hass.tasks), 0)
        self.assertEqual(len(hass.bus.listeners), 1)
        self.assertTrue(hass.data[const.DOMAIN][adoption._AUTO_ADOPTION_STARTED])

        # The startup listener re-runs the scan once states are live.
        hass.is_running = True
        try:
            with patch.object(
                adoption, "discover_sources", return_value=[_Candidate("new")]
            ):
                hass.data[const.DOMAIN][adoption._AUTO_ADOPTION_STARTED] = False
                self.assertEqual(adoption.start_auto_adoption(hass), 1)
        finally:
            hass.close_tasks()

    def test_manually_configured_charger_is_not_adopted_again(self) -> None:
        # A manual entry stores no source_device_id, only mapped entity ids.
        hass = _Hass(
            entry_data=(
                {
                    "source_status": "sensor.prime_charging_status",
                    "name": "Wallbox Prime",
                },
            )
        )
        candidates = [
            _Candidate(
                "prime-device",
                {"source_status": "sensor.prime_charging_status"},
            ),
            _Candidate("other-device", {"source_status": "sensor.other_status"}),
        ]
        try:
            with patch.object(adoption, "discover_sources", return_value=candidates):
                self.assertEqual(adoption.start_auto_adoption(hass), 1)
            self.assertEqual(len(hass.tasks), 1)
        finally:
            hass.close_tasks()


if __name__ == "__main__":
    unittest.main()
