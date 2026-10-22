"""Portable CSV and JSON serialization for reproducible run artifacts."""
import csv
import io
import json
import numpy as np


def results_csv(result: dict, profiles: dict, config, controller: str = "Rule-based") -> str:
    out = io.StringIO()
    fields = ["step", "time_hours", "available_pv_kw", "critical_demand_kw", "flexible_demand_kw", "load_kw",
              "served_critical_kw", "served_flexible_kw", "grid_available", "grid_import_kw", "grid_export_kw",
              "generator_kw", "battery_charge_kw", "battery_discharge_kw", "battery_energy_kwh", "soc_percent",
              "curtailed_pv_kw", "unserved_critical_kw", "unserved_flexible_kw", "unserved_critical_kwh_step",
              "unserved_flexible_kwh_step", "cost", "emissions_kg", "events", "controller"]
    writer = csv.DictWriter(out, fieldnames=fields); writer.writeheader()
    for i in range(len(result["time"])):
        writer.writerow({"step": i, "time_hours": result["time"][i], "available_pv_kw": result["pv"][i],
            "critical_demand_kw": result["critical_demand"][i], "flexible_demand_kw": result["flexible_demand"][i], "load_kw": result["load"][i],
            "served_critical_kw": result["served_critical"][i], "served_flexible_kw": result["served_flexible"][i],
            "grid_available": bool(result["grid_available"][i]), "grid_import_kw": result["grid_import"][i], "grid_export_kw": result["grid_export"][i],
            "generator_kw": result["generator"][i], "battery_charge_kw": result["charge"][i], "battery_discharge_kw": result["discharge"][i],
            "battery_energy_kwh": result["energy"][i], "soc_percent": result["soc"][i], "curtailed_pv_kw": result["curtailed"][i],
            "unserved_critical_kw": result["unserved_critical"][i], "unserved_flexible_kw": result["unserved_flexible"][i],
            "unserved_critical_kwh_step": result["unserved_critical"][i] * config.step_minutes / 60,
            "unserved_flexible_kwh_step": result["unserved_flexible"][i] * config.step_minutes / 60,
            "cost": result["cost"][i], "emissions_kg": result["emissions"][i], "events": result["events"][i], "controller": controller})
    return out.getvalue()


def config_json(config) -> str:
    events = []
    if config.scenario in ("Grid outage", "Combined storm"):
        events.append({"type": "grid_outage", "start_hours": config.outage_start, "duration_hours": config.outage_duration})
    if config.scenario in ("Solar drop", "Combined storm"):
        events.append({"type": "solar_drop", "start_hours": config.solar_drop_start,
                       "duration_hours": config.solar_drop_duration, "reduction_percent": config.solar_drop_percent})
    if config.scenario in ("Demand spike", "Combined storm"):
        events.append({"type": "demand_spike", "start_hours": config.spike_start,
                       "duration_hours": config.spike_duration, "increase_percent": config.spike_percent,
                       "affected_loads": config.spike_loads})
    if config.scenario == "High-price period":
        events.append({"type": "high_price", "start_hours": config.spike_start,
                       "duration_hours": config.spike_duration, "tariff_multiplier": 3})
    return json.dumps({"config": config.to_dict(), "seed": config.seed, "synthetic_profiles": True, "events": events}, indent=2)
