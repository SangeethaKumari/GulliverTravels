"""Ambient Travel Companion — capstone implementation.

Implements the four-pillar architecture from the capstone brief:
- Real-time monitoring via mocked MCP-style tools
- Probabilistic reasoning via a Time/Risk/Impact committee
- Orchestrated decision policy with thresholds
- Action layer (notify, negotiate, book ride)
- DSPy-style notification composer with heuristic fallback

Run scenarios A/B/C/D via:
    python -m travelagent.companion.runner
"""
