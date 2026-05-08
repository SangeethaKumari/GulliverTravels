"""Run all canonical scenarios and pretty-print the results.

Usage:
    PYTHONPATH=backend/src python -m travelagent.companion.runner
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from . import mocks
from .composer import HeuristicComposer
from .orchestrator import Orchestrator
from .scenarios import ALL_SCENARIOS


SEPARATOR = "=" * 78


def run_one(scenario_factory) -> dict:
    state = scenario_factory()
    mocks.set_scenario(state)
    mocks.set_now(datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc))

    orch = Orchestrator(user_name="Sam", composer=HeuristicComposer())
    result = orch.run_cycle(flight_number="UA123", user_id="user-1")

    summary = {
        "scenario": state.name,
        "decision": result.decision.decision,
        "p_on_time": result.decision.p_on_time,
        "adjusted_p_on_time": result.decision.adjusted_p_on_time,
        "meeting_weight": result.decision.meeting_weight,
        "risk_multiplier": result.decision.risk_multiplier,
        "rationale": result.decision.rationale,
        "risk_factors": result.decision.risk_output.risk_factors,
        "notifications": [
            {
                "channel": n["channel"],
                "to": n["to"],
                "message": n["message"],
                "rewards": n["rewards"],
            }
            for n in result.log.notifications
        ],
        "calendar_updates": result.log.calendar_updates,
        "rides_booked": result.log.rides_booked,
        "rides_cancelled": result.log.rides_cancelled,
    }
    return summary


def main():
    print(SEPARATOR)
    print(" Ambient Travel Companion — Scenario Run")
    print(SEPARATOR)

    for factory in ALL_SCENARIOS:
        summary = run_one(factory)
        print()
        print(f"--- {summary['scenario']} ---")
        print(f"Decision           : {summary['decision']}")
        print(f"P(on time)         : {summary['p_on_time']}")
        print(f"Adjusted P(on time): {summary['adjusted_p_on_time']}")
        print(f"Meeting weight     : {summary['meeting_weight']}")
        print(f"Risk multiplier    : {summary['risk_multiplier']}")
        print(f"Risk factors       : {summary['risk_factors']}")
        print(f"Rationale          : {summary['rationale']}")
        if summary["notifications"]:
            print("Notifications:")
            for n in summary["notifications"]:
                print(f"  [{n['channel']}] -> {n['to']}")
                print(f"    msg     : {n['message']}")
                print(f"    rewards : {n['rewards']}")
        if summary["calendar_updates"]:
            print(f"Calendar proposals : "
                  f"{[u['proposals'] for u in summary['calendar_updates']]}")
        if summary["rides_booked"]:
            print("Rides booked:")
            for r in summary["rides_booked"]:
                print(f"  {r['service']} -- {r['driverName']} ({r['vehicleModel']} "
                      f"{r['plate']}), pickup {r['pickupTime']}, "
                      f"ETA {r['etaMinutes']}m, ${r['estimatedFareUSD']}")
    print()
    print(SEPARATOR)
    print(" Done.")
    print(SEPARATOR)


if __name__ == "__main__":
    main()
