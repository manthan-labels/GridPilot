"""Typed configuration and input validation for GridPilot."""
from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any


@dataclass
class Config:
    duration_hours: float = 24
    step_minutes: int = 5
    start_hour: float = 0
    pv_capacity_kw: float = 50
    solar_scale: float = 1.0
    battery_capacity_kwh: float = 100
    charge_limit_kw: float = 30
    discharge_limit_kw: float = 30
    initial_soc: float = .80
    min_soc: float = .20
    max_soc: float = .95
    round_trip_efficiency: float = .90
    battery_enabled: bool = True
    grid_limit_kw: float = 60
    grid_export_limit_kw: float = 0
    export_enabled: bool = False
    grid_price: float = .20
    export_price: float = .05
    grid_emissions: float = .40
    generator_capacity_kw: float = 40
    generator_enabled: bool = True
    generator_cost: float = .45
    generator_emissions: float = .70
    critical_kw: float = 20
    flexible_kw: float = 15
    ev_enabled: bool = False
    ev_kw: float = 0
    hvac_enabled: bool = False
    hvac_kw: float = 0
    demand_scale: float = 1.0
    weather: str = "Clear"
    demand_profile: str = "Typical day"
    variability: bool = False
    seed: int = 42
    objective: str = "Balanced"
    currency_label: str = "$"
    carbon_price: float = 0
    target_soc: float | None = None
    scenario: str = "Normal day"
    outage_start: float = 12
    outage_duration: float = 2
    solar_drop_start: float = 12
    solar_drop_duration: float = 3
    solar_drop_percent: float = 70
    spike_start: float = 17
    spike_duration: float = 2
    spike_percent: float = 50
    spike_loads: list[str] = field(default_factory=lambda: ["Critical", "Flexible"])
    shed_limit: float = 1.0

    def validate(self) -> None:
        numeric = {k: v for k, v in asdict(self).items() if isinstance(v, (int, float)) and v is not None}
        if not all(isfinite(float(v)) for v in numeric.values()):
            raise ValueError("All numeric settings must be finite.")
        ranges = {
            "duration_hours": (1, 72), "step_minutes": (1, 15), "pv_capacity_kw": (0, 200),
            "solar_scale": (0, 1.5), "battery_capacity_kwh": (10, 500), "charge_limit_kw": (0, 200),
            "discharge_limit_kw": (0, 200), "initial_soc": (0, 1), "min_soc": (0, .5), "max_soc": (.5, 1),
            "round_trip_efficiency": (.7, 1), "grid_limit_kw": (0, 500), "grid_export_limit_kw": (0, 500),
            "grid_price": (0, 5), "export_price": (0, 5), "grid_emissions": (0, 5),
            "generator_capacity_kw": (0, 300), "generator_cost": (0, 10), "generator_emissions": (0, 10),
            "critical_kw": (0, 200), "flexible_kw": (0, 200), "ev_kw": (0, 100), "hvac_kw": (0, 100),
            "demand_scale": (.5, 2), "carbon_price": (0, 10), "shed_limit": (0, 1),
        }
        for key, (lo, hi) in ranges.items():
            value = getattr(self, key)
            if not lo <= value <= hi:
                raise ValueError(f"{key} must be between {lo} and {hi}.")
        if self.step_minutes not in (1, 5, 10, 15):
            raise ValueError("Time step must be 1, 5, 10, or 15 minutes.")
        if not 0 <= self.start_hour <= 23:
            raise ValueError("Start hour must be between 0 and 23.")
        if self.weather not in {"Clear", "Partly cloudy", "Cloudy", "User adjusted"}:
            raise ValueError("Choose a supported weather profile.")
        if self.demand_profile not in {"Typical day", "High demand", "Low demand", "User adjusted"}:
            raise ValueError("Choose a supported demand profile.")
        if self.scenario not in {"Normal day", "Grid outage", "Solar drop", "Demand spike", "Combined storm", "Low battery at start", "High-price period"}:
            raise ValueError("Choose a supported scenario.")
        if self.objective not in {"Lowest cost", "Lower emissions", "Balanced", "Maximum resilience"}:
            raise ValueError("Choose a supported dispatch objective.")
        if not self.currency_label.strip():
            raise ValueError("Currency label cannot be empty.")
        if not self.min_soc <= self.initial_soc <= self.max_soc:
            raise ValueError("SOC must satisfy minimum ≤ initial ≤ maximum.")
        if self.target_soc is not None and not self.min_soc <= self.target_soc <= self.max_soc:
            raise ValueError("Target SOC must be within the battery SOC limits.")
        events = []
        if self.scenario in ("Grid outage", "Combined storm"): events.append((self.outage_start, self.outage_duration))
        if self.scenario in ("Solar drop", "Combined storm"): events.append((self.solar_drop_start, self.solar_drop_duration))
        if self.scenario in ("Demand spike", "Combined storm", "High-price period"): events.append((self.spike_start, self.spike_duration))
        for start, duration in events:
            if start < 0 or duration <= 0 or start + duration > self.duration_hours:
                raise ValueError("Scenario event start and duration must fit within the simulation horizon.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

