"""Demo runner for multi-step timeline simulations.

Usage:
    PYTHONPATH=backend/src python -m travelagent.companion.demo_timeline
"""

from __future__ import annotations

import copy

from .composer import HeuristicComposer
from .monitor import AmbientOrchestrator
from .persistence import DB
from .timelines import ALL_TIMELINES

SEP = "=" * 70


def run_timeline(name: str, steps_factory, db: DB):
    print(f"\n{SEP}")
    print(f" Timeline: {name}")
    print(SEP)

    steps = [copy.deepcopy(s) for s in steps_factory()]
    trip_id = f"demo-{name}"
    orch = AmbientOrchestrator(db=db, user_name="Sam",
                                composer=HeuristicComposer())
    results = orch.simulate_timeline(trip_id, "UA123", "user-1", steps)

    for r in results:
        flag = "*" if r["material_change"] else " "
        acts = ", ".join(r["actions"]) if r["actions"] else "-"
        delay = r.get("delay_minutes", "")
        wx = r.get("weather", "?")
        traf = r.get("traffic", "?")
        print(
            f"  [{flag}] iter {r['iteration']:2d}: {r['decision']:10s} | "
            f"flight={r['flight_status']:10s} "
            f"delay={str(delay):>4s}m  wx={wx:6s}  traffic={traf:6s} | "
            f"actions: {acts}"
        )
        if r["material_change"]:
            print(f"       rationale: {r['rationale']}")

    snaps = db.get_snapshots(trip_id)
    runs = db.get_committee_runs(trip_id)
    actions = db.get_actions(trip_id)
    print(f"\n  DB audit: {len(snaps)} snapshots, {len(runs)} committee runs, "
          f"{len(actions)} actions persisted")


def main():
    print(SEP)
    print(" Ambient Travel Companion — Timeline Simulations")
    print(SEP)

    db = DB(":memory:")
    for name, factory in ALL_TIMELINES.items():
        run_timeline(name, factory, db)
    db.close()

    print(f"\n{SEP}")
    print(" Done.")
    print(SEP)


if __name__ == "__main__":
    main()
