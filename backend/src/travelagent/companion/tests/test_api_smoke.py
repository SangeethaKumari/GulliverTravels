"""Quick HTTP smoke test against the running companion API (port 8000)."""

import httpx

base = "http://localhost:8000"

# Health
r = httpx.get(f"{base}/health")
assert r.status_code == 200
print("Health: OK")

# Scenario A: SILENT
r = httpx.post(f"{base}/companion/run", json={"scenario": "A"})
d = r.json()
print(f"A: {d['decision']} (p={d['adjusted_p_on_time']}, weight={d['meeting_weight']})")
assert d["decision"] == "SILENT", f"Expected SILENT, got {d['decision']}"

# Scenario B: NEGOTIATE
r = httpx.post(f"{base}/companion/run", json={"scenario": "B"})
d = r.json()
print(f"B: {d['decision']} (p={d['adjusted_p_on_time']}, weight={d['meeting_weight']})")
print(f"   Risk factors: {d['risk_factors']}")
print(f"   Notifications: {len(d['notifications'])}")
print(f"   Rides booked: {len(d['rides_booked'])}")
print(f"   Msg preview: {d['notifications'][0]['message'][:100]}...")
print(f"   Rewards: {d['notifications'][0]['rewards']}")
assert d["decision"] == "NEGOTIATE"
assert len(d["notifications"]) == 2  # user + attendees
assert len(d["rides_booked"]) == 1
assert len(d["calendar_updates"]) == 1

# Scenario C: SILENT
r = httpx.post(f"{base}/companion/run", json={"scenario": "C"})
d = r.json()
print(f"C: {d['decision']} (p={d['adjusted_p_on_time']})")
assert d["decision"] == "SILENT"

# Scenario D: CANCEL
r = httpx.post(f"{base}/companion/run", json={"scenario": "D"})
d = r.json()
print(f"D: {d['decision']} (notifications={len(d['notifications'])}, cal_updates={len(d['calendar_updates'])})")
assert d["decision"] == "CANCEL"
assert len(d["notifications"]) >= 1
assert len(d["calendar_updates"]) == 1

# Tools listing
r = httpx.get(f"{base}/companion/tools")
d = r.json()
print(f"Tools: {[t['name'] for t in d['tools']]}")

print()
print("ALL API TESTS PASSED")
