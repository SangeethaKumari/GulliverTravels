"""The four canonical test scenarios from the brief (pp. 60).

  A. Minor Delay, Light Traffic, Low-weight meeting       → SILENT
  B. Major Delay, Heavy Traffic, Critical Board meeting    → NEGOTIATE
  C. On time                                                → SILENT
  D. Cancellation                                           → CANCEL
"""

from __future__ import annotations

from .mocks import ScenarioState


def scenario_A() -> ScenarioState:
    return ScenarioState(
        name="A: Minor Delay, Light Traffic",
        flight_status="delayed",
        delay_minutes=30,
        delay_trend="stable",
        delay_reason="late inbound aircraft",
        weather_condition="clear",
        weather_trend="stable",
        traffic_level="low",
        drive_time_minutes=22,
        meeting_title="1:1 with Alex",
        meeting_attendees=["alex@example.com"],
        meeting_keywords=[],
        ride_eta_minutes=8,
    )


def scenario_B() -> ScenarioState:
    return ScenarioState(
        name="B: Major Delay, Heavy Traffic, Board Meeting",
        flight_status="delayed",
        delay_minutes=95,
        delay_trend="increasing",
        delay_reason="mechanical issue",
        weather_condition="rain",
        weather_trend="worsening",
        traffic_level="high",
        drive_time_minutes=55,
        meeting_title="Board Meeting with CEO",
        meeting_attendees=[
            "ceo@example.com", "cfo@example.com", "chair@example.com",
            "dir1@example.com", "dir2@example.com", "dir3@example.com",
            "dir4@example.com", "dir5@example.com", "dir6@example.com",
            "dir7@example.com",
        ],
        meeting_keywords=["board", "ceo", "critical"],
        ride_eta_minutes=18,
    )


def scenario_C() -> ScenarioState:
    return ScenarioState(
        name="C: On Time",
        flight_status="on_time",
        delay_minutes=0,
        delay_trend="stable",
        delay_reason="",
        weather_condition="clear",
        weather_trend="stable",
        traffic_level="low",
        drive_time_minutes=22,
        meeting_title="Project Sync",
        meeting_attendees=["alex@example.com", "jordan@example.com"],
        meeting_keywords=[],
        ride_eta_minutes=8,
    )


def scenario_D() -> ScenarioState:
    return ScenarioState(
        name="D: Cancellation",
        flight_status="cancelled",
        delay_minutes=999,
        delay_trend="stable",
        delay_reason="airline cancellation",
        weather_condition="snow",
        weather_trend="worsening",
        traffic_level="medium",
        drive_time_minutes=35,
        meeting_title="Client Pitch",
        meeting_attendees=["client@bigco.com", "ceo@example.com"],
        meeting_keywords=["client", "presentation"],
        ride_eta_minutes=15,
    )


ALL_SCENARIOS = [scenario_A, scenario_B, scenario_C, scenario_D]
