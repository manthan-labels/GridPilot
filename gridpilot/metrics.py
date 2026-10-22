"""KPI definitions for time-step simulation results."""
import numpy as np


def summarize(result: dict, config) -> dict[str, float]:
    dt = config.step_minutes / 60
    energy = lambda key: float(np.sum(result[key]) * dt)
    return {
        "load_kwh": energy("load"), "pv_kwh": energy("pv"), "grid_kwh": energy("grid_import"),
        "generator_kwh": energy("generator"), "export_kwh": energy("grid_export"),
        "unserved_critical_kwh": energy("unserved_critical"), "unserved_flexible_kwh": energy("unserved_flexible"),
        "cost": float(np.sum(result["cost"])), "emissions_kg": float(np.sum(result["emissions"])),
        "min_soc": float(min(config.initial_soc * 100, np.min(result["soc"]))) if len(result["soc"]) else config.initial_soc * 100,
        "final_soc": float(result["soc"][-1]) if len(result["soc"]) else config.initial_soc * 100,
        "renewable_share": energy("pv") / max(1e-12, energy("load")),
    }
