"""Scenario event transformations shared by every controller."""
from .config import Config
import numpy as np


def apply_scenario(config: Config, profiles: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    p = {k: v.copy() for k, v in profiles.items()}
    t, dt = p["hours"], config.step_minutes / 60
    n = len(t)
    p["grid_available"] = np.ones(n, dtype=bool)
    p["tariff"] = np.full(n, config.grid_price)
    p["events"] = np.full(n, "", dtype=object)
    def window(start: float, duration: float) -> np.ndarray:
        return (t >= start - 1e-9) & (t < start + duration - 1e-9)
    def label(mask: np.ndarray, text: str) -> None:
        p["events"][mask] = np.where(p["events"][mask] == "", text, p["events"][mask] + ", " + text)
    scenario = config.scenario
    if scenario in ("Grid outage", "Combined storm"):
        mask = window(config.outage_start, config.outage_duration)
        p["grid_available"][mask] = False
        label(mask, "Grid outage")
    if scenario in ("Solar drop", "Combined storm"):
        mask = window(config.solar_drop_start, config.solar_drop_duration)
        p["solar_factor"][mask] *= 1 - config.solar_drop_percent / 100
        label(mask, "Solar drop")
    if scenario in ("Demand spike", "Combined storm"):
        mask = window(config.spike_start, config.spike_duration)
        groups = config.spike_loads or ["Critical", "Flexible"]
        for name in ("critical", "flexible", "ev", "hvac"):
            if name.title() in groups:
                p[f"{name}_demand"][mask] *= 1 + config.spike_percent / 100
        label(mask, "Demand spike")
    if scenario == "Low battery at start":
        config.initial_soc = max(config.min_soc, min(config.initial_soc, config.min_soc + .05))
    if scenario == "High-price period":
        mask = window(config.spike_start, config.spike_duration)
        p["tariff"][mask] *= 3
        label(mask, "High tariff")
    return p

