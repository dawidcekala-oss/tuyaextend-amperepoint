"""The charging-current slider must respect the limits of the real charger.

One tuya-local profile covers the whole Q Series, so its declared range is the
union of every generation (6-48 A). The AmperePoint slider has to narrow that
back down, otherwise a 16 A Q11 would offer 48 A.
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import load_integration_module  # noqa: E402

number = load_integration_module("number")
models = load_integration_module("models")

Q11 = models.get_model("q11")
Q37 = models.get_model("q37")


class _States:
    def __init__(self, entity_id: str | None, attributes: dict | None) -> None:
        self._entity_id = entity_id
        self._attributes = attributes

    def get(self, entity_id):
        if entity_id != self._entity_id or self._attributes is None:
            return None
        return types.SimpleNamespace(attributes=self._attributes)


class _Coordinator:
    """Only the surface the number entity touches."""

    def __init__(self, model, *, source_attributes=None, dp=None) -> None:
        self.model_limits = model
        self._source = "number.q_series_charging_current" if source_attributes else None
        self.hass = types.SimpleNamespace(
            states=_States(self._source, source_attributes)
        )
        self._dp = dp or {}

    def _config(self, _key):
        return self._source

    def dp_definition(self, _code):
        return self._dp


def _slider(coordinator):
    entity = number.AmperePointCurrentLimitNumber.__new__(
        number.AmperePointCurrentLimitNumber
    )
    entity.coordinator = coordinator
    return entity


class CurrentLimitRangeTests(unittest.TestCase):
    def test_series_profile_is_narrowed_to_a_single_phase_charger(self) -> None:
        # The universal profile declares 6-48 A; a Q11 tops out at 16 A.
        slider = _slider(_Coordinator(Q11, source_attributes={"min": 6, "max": 48}))
        self.assertEqual(slider.native_min_value, 6.0)
        self.assertEqual(slider.native_max_value, 16.0)

    def test_three_phase_charger_keeps_the_full_range(self) -> None:
        slider = _slider(_Coordinator(Q37, source_attributes={"min": 6, "max": 48}))
        self.assertEqual(slider.native_min_value, 6.0)
        self.assertEqual(slider.native_max_value, 48.0)

    def test_datapoint_definition_is_narrowed_too(self) -> None:
        # Direct LAN control reads the range from the datapoint instead.
        slider = _slider(_Coordinator(Q11, dp={"min": 6, "max": 48}))
        self.assertEqual(slider.native_max_value, 16.0)

    def test_source_below_the_model_minimum_does_not_win(self) -> None:
        slider = _slider(_Coordinator(Q11, source_attributes={"min": 0, "max": 48}))
        self.assertEqual(slider.native_min_value, float(Q11.min_current_a))

    def test_without_any_source_the_model_decides(self) -> None:
        slider = _slider(_Coordinator(Q37))
        self.assertEqual(slider.native_min_value, float(Q37.min_current_a))
        self.assertEqual(slider.native_max_value, float(Q37.max_current_a))

    def test_a_narrower_charger_is_not_widened(self) -> None:
        # A profile that already knows the exact charger stays authoritative.
        slider = _slider(_Coordinator(Q37, source_attributes={"min": 6, "max": 32}))
        self.assertEqual(slider.native_max_value, 32.0)


if __name__ == "__main__":
    unittest.main()
