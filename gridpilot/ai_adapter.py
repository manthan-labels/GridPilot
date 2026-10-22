"""Validated future goal schema; deliberately contains no model or API integration."""
from dataclasses import dataclass, replace
from .config import Config


@dataclass(frozen=True)
class StructuredGoal:
    objective: str = "Balanced"
    minimum_soc: float | None = None
    preserve_critical_loads: bool = True
    backup_policy: str = "as_needed"
    outage_duration_hours: float | None = None

    def validate(self, config: Config) -> None:
        if self.objective not in {"Lowest cost", "Lower emissions", "Balanced", "Maximum resilience"}:
            raise ValueError("Unsupported objective.")
        if self.backup_policy not in {"as_needed", "disabled"}:
            raise ValueError("Unsupported backup policy.")
        if not self.preserve_critical_loads:
            raise ValueError("This prototype always preserves critical load priority.")
        if self.minimum_soc is not None and not config.min_soc <= self.minimum_soc <= config.max_soc:
            raise ValueError("Requested minimum SOC must fit the configured battery SOC range.")
        if self.outage_duration_hours is not None and not 0 < self.outage_duration_hours <= config.duration_hours:
            raise ValueError("Requested outage duration must fit within the simulation horizon.")


def apply_goal(config: Config, goal: StructuredGoal) -> Config:
    """Return a validated config copy; never mutate dispatch state or bypass physical limits."""
    goal.validate(config)
    start = config.outage_start
    scenario = config.scenario
    duration = config.outage_duration
    if goal.outage_duration_hours is not None:
        duration = goal.outage_duration_hours
        if start + duration > config.duration_hours: start = max(0, config.duration_hours - duration)
        if scenario not in {"Combined storm", "Grid outage"}: scenario = "Grid outage"
    updated = replace(config, scenario=scenario, outage_start=start, outage_duration=duration, objective=goal.objective,
                      min_soc=goal.minimum_soc if goal.minimum_soc is not None else config.min_soc,
                      generator_enabled=config.generator_enabled and goal.backup_policy != "disabled")
    updated.validate()
    return updated
