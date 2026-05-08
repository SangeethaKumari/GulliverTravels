"""End-to-end scenario tests for the Ambient Travel Companion.

Verifies decision policy and action dispatch for the four canonical
scenarios from the brief.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from travelagent.companion import mocks
from travelagent.companion.composer import HeuristicComposer
from travelagent.companion.orchestrator import (DECISION_CANCEL,
                                                 DECISION_NEGOTIATE,
                                                 DECISION_SILENT, Orchestrator)
from travelagent.companion.scenarios import (scenario_A, scenario_B,
                                              scenario_C, scenario_D)


def _run(factory):
    mocks.set_scenario(factory())
    mocks.set_now(datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc))
    orch = Orchestrator(user_name="Sam", composer=HeuristicComposer())
    return orch.run_cycle()


def test_scenario_A_silent():
    result = _run(scenario_A)
    assert result.decision.decision == DECISION_SILENT
    assert result.log.notifications == []
    assert result.log.rides_booked == []


def test_scenario_B_negotiates_and_books_ride():
    result = _run(scenario_B)
    assert result.decision.decision == DECISION_NEGOTIATE
    assert result.decision.meeting_weight > 0.7
    # Both user heads-up and attendee notification should be sent
    channels = {n["channel"] for n in result.log.notifications}
    assert "user" in channels and "attendees" in channels
    assert len(result.log.rides_booked) == 1
    assert len(result.log.calendar_updates) == 1
    # Notification quality: composite reward should be respectable
    rewards = result.log.notifications[0]["rewards"]
    assert rewards["composite"] >= 0.6
    assert rewards["r_concise"] == 1.0  # under 120 words


def test_scenario_C_silent_on_time():
    result = _run(scenario_C)
    assert result.decision.decision == DECISION_SILENT
    assert result.decision.p_on_time >= 0.85
    assert result.log.notifications == []


def test_scenario_D_cancellation():
    result = _run(scenario_D)
    assert result.decision.decision == DECISION_CANCEL
    assert len(result.log.calendar_updates) == 1
    assert len(result.log.notifications) >= 1


def test_notification_under_120_words():
    result = _run(scenario_B)
    msg = result.log.notifications[0]["message"]
    assert len(msg.split()) <= 120


def test_proposed_times_count():
    result = _run(scenario_B)
    update = result.log.calendar_updates[0]
    assert len(update["proposals"]) == 3
