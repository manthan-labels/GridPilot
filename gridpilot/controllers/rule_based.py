"""Transparent priority-based dispatch controller."""
import numpy as np
from ..config import Config


LOADS = ("critical", "flexible", "ev", "hvac")


def dispatch(config: Config, profiles: dict[str, np.ndarray], controller_name: str = "Rule-based") -> dict[str, np.ndarray]:
    dt = config.step_minutes / 60
    n = len(profiles["hours"])
    keys = ["pv", "load", "served_critical", "served_flexible", "unserved_critical", "unserved_flexible", "grid_import", "grid_export", "generator", "charge", "discharge", "energy", "soc", "curtailed", "cost", "emissions", "critical_demand", "flexible_demand"]
    r = {k: np.zeros(n) for k in keys}
    energy = config.battery_capacity_kwh * config.initial_soc
    emin, emax = config.battery_capacity_kwh * config.min_soc, config.battery_capacity_kwh * config.max_soc
    eta = config.round_trip_efficiency ** .5
    for i in range(n):
        pv = config.pv_capacity_kw * profiles["solar_factor"][i]
        demands = {k: profiles[f"{k}_demand"][i] for k in LOADS}
        critical = demands["critical"]
        flex = sum(demands[k] for k in LOADS if k != "critical")
        load = critical + flex
        served_c = min(critical, pv)
        served_f = min(flex, max(0, pv - served_c))
        pv_surplus = max(0, pv - served_c - served_f)
        residual_c, residual_f = critical - served_c, flex - served_f

        def allocate(power: float) -> float:
            nonlocal served_c, served_f, residual_c, residual_f
            to_c = min(residual_c, power)
            served_c += to_c; residual_c -= to_c; power -= to_c
            to_f = min(residual_f, power)
            served_f += to_f; residual_f -= to_f
            return to_c + to_f

        grid = min(residual_c + residual_f, config.grid_limit_kw) if profiles["grid_available"][i] else 0.0
        allocate(grid)
        remaining = residual_c + residual_f
        batt = 0.0
        if config.battery_enabled and remaining > 1e-10:
            batt = min(remaining, config.discharge_limit_kw, max(0, (energy - emin) * eta / dt))
            allocate(batt)
            energy -= batt * dt / eta
        remaining = residual_c + residual_f
        gen = min(remaining, config.generator_capacity_kw) if config.generator_enabled else 0.0
        allocate(gen)
        # Grid outage or limited sources leave shortages explicit.
        unc, unf = max(0, residual_c), max(0, residual_f)
        # If there is surplus PV, charge the battery, then export if allowed.
        charge = 0.0
        if config.battery_enabled and pv_surplus > 1e-10:
            charge = min(pv_surplus, config.charge_limit_kw, max(0, (emax - energy) / (eta * dt)))
            energy += charge * dt * eta
        excess = max(0, pv_surplus - charge)
        export = min(excess, config.grid_export_limit_kw) if config.export_enabled and profiles["grid_available"][i] else 0.0
        curtailed = excess - export
        r["pv"][i], r["load"][i] = pv, load
        r["critical_demand"][i], r["flexible_demand"][i] = critical, flex
        r["served_critical"][i], r["served_flexible"][i] = served_c, served_f
        r["unserved_critical"][i], r["unserved_flexible"][i] = unc, unf
        r["grid_import"][i], r["grid_export"][i] = grid, export
        r["generator"][i], r["charge"][i], r["discharge"][i] = gen, charge, batt
        r["energy"][i], r["soc"][i], r["curtailed"][i] = energy, 100 * energy / config.battery_capacity_kwh, curtailed
        cost = grid * profiles["tariff"][i] + gen * config.generator_cost - export * config.export_price
        emissions = grid * config.grid_emissions + gen * config.generator_emissions
        r["cost"][i] = (cost + emissions * config.carbon_price) * dt
        r["emissions"][i] = emissions * dt
    r["time"] = profiles["hours"]
    r["grid_available"] = profiles["grid_available"]
    r["events"] = profiles["events"]
    return r

