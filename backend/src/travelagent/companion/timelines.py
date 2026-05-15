"""Multi-step timeline scenarios for testing the ambient monitoring loop.

Each timeline is a list of ScenarioState snapshots at increasing time
offsets. The mock layer advances through these steps as the loop polls.
This simulates real state transitions like "storm hits at iteration 7."
"""

from __future__ import annotations

from .mocks import ScenarioState


def timeline_storm_at_iteration_7() -> list[dict]:
    """8 iterations: stable for 6, storm hits at 7, delay worsens at 8.
    
    Expected decisions:
      iter 1-6:  SILENT (green, low risk, low impact)
      iter 7:    HEADS_UP or NEGOTIATE (weather worsens, delay increases)
      iter 8:    NEGOTIATE (major delay, high risk)
    """
    base = dict(
        flight_status="on_time",
        delay_minutes=0,
        delay_trend="stable",
        delay_reason="",
        weather_condition="clear",
        weather_trend="stable",
        traffic_level="low",
        drive_time_minutes=22,
        meeting_title="Board Meeting with CEO",
        meeting_attendees=["ceo@example.com", "cfo@example.com",
                           "dir1@example.com", "dir2@example.com"],
        meeting_keywords=["board", "ceo", "critical"],
        ride_eta_minutes=8,
    )

    steps = []
    # Iterations 1-6: everything calm
    for i in range(1, 7):
        steps.append({"time_offset_min": i * 5, **base,
                       "name": f"Storm timeline step {i}: calm"})
    # Iteration 7: storm hits
    steps.append({
        "time_offset_min": 35,
        **{**base,
           "weather_condition": "rain",
           "weather_trend": "worsening",
           "delay_minutes": 25,
           "delay_trend": "increasing",
           "delay_reason": "weather hold",
           "traffic_level": "medium",
           "drive_time_minutes": 35,
           "name": "Storm timeline step 7: storm hits"},
    })
    # Iteration 8: delay worsens
    steps.append({
        "time_offset_min": 40,
        **{**base,
           "weather_condition": "rain",
           "weather_trend": "worsening",
           "delay_minutes": 65,
           "delay_trend": "increasing",
           "delay_reason": "severe weather ground stop",
           "traffic_level": "high",
           "drive_time_minutes": 50,
           "name": "Storm timeline step 8: delay worsens"},
    })
    return steps


def timeline_friday_evening() -> list[dict]:
    """Flight delayed on Friday evening — reschedule should push to Monday.
    
    Expected: NEGOTIATE with proposed slots on Monday.
    """
    return [
        {
            "time_offset_min": 0,
            "name": "Friday evening: flight delayed",
            "flight_status": "delayed",
            "delay_minutes": 90,
            "delay_trend": "stable",
            "delay_reason": "crew scheduling",
            "weather_condition": "clear",
            "weather_trend": "stable",
            "traffic_level": "medium",
            "drive_time_minutes": 30,
            "meeting_title": "Client Presentation",
            "meeting_attendees": ["client@bigco.com", "ceo@example.com"],
            "meeting_keywords": ["client", "presentation"],
            "ride_eta_minutes": 10,
        }
    ]


def timeline_cancellation_recovery() -> list[dict]:
    """Flight cancelled then rebooked — system should CANCEL then re-assess.
    
    Steps:
      1: On time
      2: Cancelled
      3: Still cancelled (no change — should NOT re-run committee)
    """
    base_attendees = ["partner@firm.com"]
    return [
        {
            "time_offset_min": 0,
            "name": "Cancel recovery step 1: on time",
            "flight_status": "on_time",
            "delay_minutes": 0,
            "delay_trend": "stable",
            "delay_reason": "",
            "weather_condition": "clear",
            "weather_trend": "stable",
            "traffic_level": "low",
            "drive_time_minutes": 22,
            "meeting_title": "Partner Meeting",
            "meeting_attendees": base_attendees,
            "meeting_keywords": [],
            "ride_eta_minutes": 8,
        },
        {
            "time_offset_min": 5,
            "name": "Cancel recovery step 2: cancelled",
            "flight_status": "cancelled",
            "delay_minutes": 999,
            "delay_trend": "stable",
            "delay_reason": "airline cancellation",
            "weather_condition": "snow",
            "weather_trend": "worsening",
            "traffic_level": "medium",
            "drive_time_minutes": 35,
            "meeting_title": "Partner Meeting",
            "meeting_attendees": base_attendees,
            "meeting_keywords": [],
            "ride_eta_minutes": 15,
        },
        {
            "time_offset_min": 10,
            "name": "Cancel recovery step 3: still cancelled",
            "flight_status": "cancelled",
            "delay_minutes": 999,
            "delay_trend": "stable",
            "delay_reason": "airline cancellation",
            "weather_condition": "snow",
            "weather_trend": "worsening",
            "traffic_level": "medium",
            "drive_time_minutes": 35,
            "meeting_title": "Partner Meeting",
            "meeting_attendees": base_attendees,
            "meeting_keywords": [],
            "ride_eta_minutes": 15,
        },
    ]


def timeline_landed() -> list[dict]:
    """Flight on time then lands — loop should terminate."""
    return [
        {
            "time_offset_min": 0,
            "name": "Landed step 1: in air",
            "flight_status": "on_time",
            "delay_minutes": 0,
            "delay_trend": "stable",
            "delay_reason": "",
            "weather_condition": "clear",
            "weather_trend": "stable",
            "traffic_level": "low",
            "drive_time_minutes": 22,
            "meeting_title": "Team Sync",
            "meeting_attendees": ["alex@example.com"],
            "meeting_keywords": [],
            "ride_eta_minutes": 8,
        },
        {
            "time_offset_min": 5,
            "name": "Landed step 2: landed",
            "flight_status": "landed",
            "delay_minutes": 0,
            "delay_trend": "stable",
            "delay_reason": "",
            "weather_condition": "clear",
            "weather_trend": "stable",
            "traffic_level": "low",
            "drive_time_minutes": 22,
            "meeting_title": "Team Sync",
            "meeting_attendees": ["alex@example.com"],
            "meeting_keywords": [],
            "ride_eta_minutes": 8,
        },
    ]


ALL_TIMELINES = {
    "storm": timeline_storm_at_iteration_7,
    "friday": timeline_friday_evening,
    "cancel_recovery": timeline_cancellation_recovery,
    "landed": timeline_landed,
}
