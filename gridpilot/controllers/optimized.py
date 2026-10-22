"""Optional linear-program dispatch; requires SciPy. Physical bounds are hard constraints."""
import numpy as np
from ..config import Config


def dispatch(config: Config, profiles: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    try:
        from scipy.optimize import Bounds, LinearConstraint, milp
        from scipy.sparse import lil_matrix, vstack
    except ImportError as exc:
        raise RuntimeError("Optimized dispatch requires SciPy. Install dependencies from requirements.txt; rule-based simulation remains available.") from exc
    n = len(profiles["hours"]); dt = config.step_minutes / 60
    names = ("grid_import", "grid_export", "generator", "charge", "discharge", "served_critical", "served_flexible", "curtailed")
    idx = {name: j for j, name in enumerate(names)}; width = len(names); size = n * width + n + 1
    def ix(i, name): return i * width + idx[name]
    e0 = n * width
    mode0 = e0 + n + 1
    grid_mode0 = mode0 + n
    size += 2 * n
    c = np.zeros(size); bounds = [(0, None)] * size
    for i in range(n):
        tariff = profiles["tariff"][i]
        grid_value = tariff + config.grid_emissions * config.carbon_price
        gen_value = config.generator_cost + config.generator_emissions * config.carbon_price
        if config.objective == "Lower emissions":
            grid_value = config.grid_emissions + tariff * .05
            gen_value = config.generator_emissions + config.generator_cost * .05
        elif config.objective == "Maximum resilience":
            grid_value = tariff + config.grid_emissions * .1
            gen_value = config.generator_cost * .7 + config.generator_emissions * .1
        elif config.objective == "Balanced":
            grid_value = tariff + config.grid_emissions * .15 + config.carbon_price * config.grid_emissions
            gen_value = config.generator_cost + config.generator_emissions * .15 + config.carbon_price * config.generator_emissions
        c[ix(i, "grid_import")] = dt * grid_value
        c[ix(i, "grid_export")] = -dt * config.export_price
        c[ix(i, "generator")] = dt * gen_value
        c[ix(i, "charge")] = dt * 1e-5; c[ix(i, "discharge")] = dt * 1e-5
        c[ix(i, "served_critical")] = -dt * 10000
        c[ix(i, "served_flexible")] = -dt * 100
        c[ix(i, "curtailed")] = dt * 1e-7
        bounds[ix(i, "grid_import")] = (0, config.grid_limit_kw if profiles["grid_available"][i] else 0)
        bounds[ix(i, "grid_export")] = (0, config.grid_export_limit_kw if config.export_enabled and profiles["grid_available"][i] else 0)
        bounds[ix(i, "generator")] = (0, config.generator_capacity_kw if config.generator_enabled else 0)
        bounds[ix(i, "charge")] = (0, config.charge_limit_kw if config.battery_enabled else 0)
        bounds[ix(i, "discharge")] = (0, config.discharge_limit_kw if config.battery_enabled else 0)
        bounds[ix(i, "served_critical")] = (0, profiles["critical_demand"][i])
        bounds[ix(i, "served_flexible")] = (0, sum(profiles[f"{k}_demand"][i] for k in ("flexible", "ev", "hvac")))
        bounds[ix(i, "curtailed")] = (0, config.pv_capacity_kw * profiles["solar_factor"][i])
    emin, emax = config.battery_capacity_kwh * config.min_soc, config.battery_capacity_kwh * config.max_soc
    for i in range(n + 1): bounds[e0 + i] = (emin, emax)
    bounds[e0] = (config.battery_capacity_kwh * config.initial_soc, config.battery_capacity_kwh * config.initial_soc)
    if config.target_soc is not None: bounds[e0 + n] = (config.battery_capacity_kwh * config.target_soc, config.battery_capacity_kwh * config.target_soc)
    for i in range(n):
        bounds[mode0 + i] = (0, 1)
        bounds[grid_mode0 + i] = (0, 1)
    eq = lil_matrix((2 * n, size)); b = np.zeros(2 * n); eta = config.round_trip_efficiency ** .5
    for i in range(n):
        # Bus power balance, with all unmet demand represented as unserved.
        for source in ("grid_import", "generator", "discharge"): eq[i, ix(i, source)] = 1
        for sink in ("grid_export", "charge", "served_critical", "served_flexible", "curtailed"): eq[i, ix(i, sink)] = -1
        b[i] = -config.pv_capacity_kw * profiles["solar_factor"][i]
        row = n + i
        eq[row, e0 + i + 1] = 1; eq[row, e0 + i] = -1
        eq[row, ix(i, "charge")] = -dt * eta
        eq[row, ix(i, "discharge")] = dt / eta
    # A binary mode variable makes simultaneous charge and discharge impossible.
    mode = lil_matrix((4 * n, size))
    ub = np.zeros(4 * n)
    for i in range(n):
        mode[2*i, ix(i, "charge")] = 1; mode[2*i, mode0+i] = -config.charge_limit_kw
        mode[2*i+1, ix(i, "discharge")] = 1; mode[2*i+1, mode0+i] = config.discharge_limit_kw
        ub[2*i+1] = config.discharge_limit_kw
        mode[2*n+2*i, ix(i, "grid_import")] = 1; mode[2*n+2*i, grid_mode0+i] = -config.grid_limit_kw
        mode[2*n+2*i+1, ix(i, "grid_export")] = 1; mode[2*n+2*i+1, grid_mode0+i] = config.grid_export_limit_kw
        ub[2*n+2*i+1] = config.grid_export_limit_kw
    constraints = LinearConstraint(vstack([eq.tocsr(), mode.tocsr()]).tocsr(),
                                   np.concatenate([b, np.full(4*n, -np.inf)]), np.concatenate([b, ub]))
    integrality = np.zeros(size, dtype=int); integrality[mode0:mode0+n] = 1; integrality[grid_mode0:grid_mode0+n] = 1
    lb = np.array([0 if low is None else low for low, _ in bounds], dtype=float)
    bound_ub = np.array([np.inf if high is None else high for _, high in bounds], dtype=float)
    sol = milp(c, integrality=integrality, bounds=Bounds(lb, bound_ub), constraints=constraints,
               options={"time_limit": 30, "mip_rel_gap": .005})
    if not sol.success: raise RuntimeError(f"Optimized dispatch failed: {sol.message}")
    v = sol.x
    out = {name: np.array([v[ix(i, name)] for i in range(n)]) for name in names}
    out["pv"] = config.pv_capacity_kw * profiles["solar_factor"]
    out["critical_demand"] = profiles["critical_demand"]
    out["flexible_demand"] = sum(profiles[f"{k}_demand"] for k in ("flexible", "ev", "hvac"))
    out["load"] = out["critical_demand"] + out["flexible_demand"]
    out["unserved_critical"] = out["critical_demand"] - out["served_critical"]
    out["unserved_flexible"] = out["flexible_demand"] - out["served_flexible"]
    out["energy"] = v[e0 + 1:e0 + n + 1]
    out["soc"] = out["energy"] / config.battery_capacity_kwh * 100
    out["cost"] = (out["grid_import"] * profiles["tariff"] + out["generator"] * config.generator_cost - out["grid_export"] * config.export_price +
                   (out["grid_import"] * config.grid_emissions + out["generator"] * config.generator_emissions) * config.carbon_price) * dt
    out["emissions"] = (out["grid_import"] * config.grid_emissions + out["generator"] * config.generator_emissions) * dt
    out["time"] = profiles["hours"]; out["grid_available"] = profiles["grid_available"]; out["events"] = profiles["events"]
    return out
