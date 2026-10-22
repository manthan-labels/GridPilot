"""Synthetic solar and demand curves; these are illustrative profiles, not forecasts."""
import numpy as np
from .config import Config


def make_profiles(config: Config) -> dict[str, np.ndarray]:
    dt = config.step_minutes / 60
    n = int(round(config.duration_hours / dt))
    t = np.arange(n) * dt
    hour = (t + config.start_hour) % 24
    daylight = np.clip(np.sin(np.pi * (hour - 6) / 12), 0, None) ** 1.6
    weather_scale = {"Clear": 1.0, "Partly cloudy": .78, "Cloudy": .48, "User adjusted": 1.0}.get(config.weather, 1.0)
    solar = np.minimum(1.0, daylight * weather_scale * config.solar_scale)
    typical = .62 + .14 * np.exp(-((hour - 8) / 2) ** 2) + .30 * np.exp(-((hour - 19) / 3) ** 2)
    demand_scale = {"Typical day": 1.0, "High demand": 1.2, "Low demand": .8, "User adjusted": 1.0}.get(config.demand_profile, 1.0)
    total_factor = typical * demand_scale * config.demand_scale
    if config.variability:
        rng = np.random.default_rng(config.seed)
        total_factor *= np.maximum(.5, 1 + rng.normal(0, .035, n))
        solar *= np.maximum(0, 1 + rng.normal(0, .025, n))
    out = {"hours": t, "hour_of_day": hour, "solar_factor": solar}
    for name, kw, on in (("critical", config.critical_kw, True), ("flexible", config.flexible_kw, True),
                         ("ev", config.ev_kw, config.ev_enabled), ("hvac", config.hvac_kw, config.hvac_enabled)):
        factor = total_factor
        if name == "ev":
            factor = np.where((hour >= 18) | (hour < 7), 1.0, .08) * demand_scale * config.demand_scale
        if name == "hvac":
            factor = (.8 + .2 * np.maximum(0, np.sin(np.pi * (hour - 6) / 12))) * demand_scale * config.demand_scale
        out[f"{name}_demand"] = kw * factor if on else np.zeros(n)
    return out

