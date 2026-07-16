from __future__ import annotations

import asyncio
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import load_integration_module  # noqa: E402

planner_module = load_integration_module("planner")


class _Coordinator:
    def __init__(self) -> None:
        self.data = {
            "source_online": True,
            "work_mode": "charge_now",
            "current_limit_a": 16.0,
            "switch_enabled": True,
        }
        self.model_limits = types.SimpleNamespace(
            min_current_a=6.0,
            max_current_a=32.0,
        )


class PlannerCommandStatusTests(unittest.TestCase):
    def test_failed_status_returns_to_idle_when_desired_state_is_settled(self) -> None:
        now = datetime.now(timezone.utc)
        planner = planner_module.AmperePointPlanner.__new__(
            planner_module.AmperePointPlanner
        )
        planner.coordinator = _Coordinator()
        planner.config = {"enabled": False, "windows": []}
        planner.override = {
            "mode": "charge",
            "until": (now + timedelta(hours=1)).isoformat(),
            "current_a": 16.0,
        }
        planner.pending = None
        planner.command_status = "failed"
        planner.last_confirmation = {
            "action": "set_current",
            "failed_at": (now - timedelta(minutes=5)).isoformat(),
            "error": "confirmation timeout",
        }
        planner.retry_after = now - timedelta(seconds=1)
        planner.managed_charging = True
        planner._state = "failed"
        planner._listeners = set()
        planner._lock = asyncio.Lock()

        asyncio.run(planner.async_evaluate("retry_expired"))

        self.assertEqual(planner.command_status, "idle")
        self.assertIsNone(planner.retry_after)
        self.assertEqual(planner.state, "override_charging")
        self.assertEqual(planner.last_confirmation["error"], "confirmation timeout")


if __name__ == "__main__":
    unittest.main()
