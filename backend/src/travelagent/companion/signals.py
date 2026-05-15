"""Signal enums and data types for the ambient agent committee.

Each agent emits a discrete signal (GREEN/YELLOW/RED or LOW/MEDIUM/HIGH)
alongside its raw numeric output. The orchestrator uses these signals
in a truth-table decision policy.
"""

from __future__ import annotations

from enum import Enum


class TimeSignal(str, Enum):
    GREEN = "GREEN"    # p_on_time >= 0.85 — comfortable
    YELLOW = "YELLOW"  # 0.60 <= p_on_time < 0.85 — tight
    RED = "RED"        # p_on_time < 0.60 — unlikely

    @classmethod
    def from_probability(cls, p: float) -> "TimeSignal":
        if p >= 0.85:
            return cls.GREEN
        if p >= 0.60:
            return cls.YELLOW
        return cls.RED


class RiskSignal(str, Enum):
    LOW = "LOW"        # multiplier < 1.15, no severe factors
    MEDIUM = "MEDIUM"  # multiplier < 1.35
    HIGH = "HIGH"      # multiplier >= 1.35 or severe factor present

    SEVERE_FACTORS = frozenset({
        "thunderstorm", "blizzard", "ground_stop",
        "adverse_weather_snow", "cascading_delays",
    })

    @classmethod
    def from_multiplier(cls, multiplier: float, factors: list) -> "RiskSignal":
        if any(f in cls.SEVERE_FACTORS for f in factors):
            return cls.HIGH
        if multiplier >= 1.35:
            return cls.HIGH
        if multiplier >= 1.15:
            return cls.MEDIUM
        return cls.LOW


class ImpactSignal(str, Enum):
    LOW = "LOW"        # weight < 0.4
    MEDIUM = "MEDIUM"  # 0.4 <= weight < 0.7
    HIGH = "HIGH"      # weight >= 0.7

    @classmethod
    def from_weight(cls, weight: float) -> "ImpactSignal":
        if weight >= 0.7:
            return cls.HIGH
        if weight >= 0.4:
            return cls.MEDIUM
        return cls.LOW


class Decision(str, Enum):
    SILENT = "SILENT"
    HEADS_UP = "HEADS_UP"
    NEGOTIATE = "NEGOTIATE"
    CANCEL = "CANCEL"

    @classmethod
    def from_signals(cls, time: TimeSignal, risk: RiskSignal,
                     impact: ImpactSignal, flight_cancelled: bool = False,
                     flight_diverted: bool = False) -> "Decision":
        """Truth-table decision policy."""
        if flight_cancelled:
            return cls.CANCEL
        if flight_diverted and impact == ImpactSignal.HIGH:
            return cls.NEGOTIATE

        # RED time → always negotiate
        if time == TimeSignal.RED:
            return cls.NEGOTIATE

        # YELLOW time
        if time == TimeSignal.YELLOW:
            if impact == ImpactSignal.HIGH:
                return cls.NEGOTIATE
            if impact == ImpactSignal.MEDIUM:
                return cls.HEADS_UP
            return cls.SILENT

        # GREEN time
        if risk == RiskSignal.HIGH and impact == ImpactSignal.HIGH:
            return cls.HEADS_UP
        if risk == RiskSignal.MEDIUM and impact == ImpactSignal.HIGH:
            return cls.HEADS_UP
        return cls.SILENT
