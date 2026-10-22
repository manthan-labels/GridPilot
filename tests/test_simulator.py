import csv
import io
import json
import unittest
import numpy as np
from gridpilot.config import Config
from gridpilot.profiles import make_profiles
from gridpilot.scenarios import apply_scenario
from gridpilot.simulator import run
from gridpilot.exports import results_csv, config_json
from gridpilot.ai_adapter import StructuredGoal, apply_goal


class SimulatorTests(unittest.TestCase):
    def test_solar_bounded_and_near_zero_at_night(self):
        c = Config(); p = make_profiles(c)
        self.assertLessEqual(np.max(p["solar_factor"]), 1)
        self.assertLess(np.max(p["solar_factor"][(p["hour_of_day"] < 5) | (p["hour_of_day"] > 20)]), .01)

    def test_scale_monotonic(self):
        a = Config(solar_scale=.7); b = Config(solar_scale=1.2)
        self.assertTrue(np.all(make_profiles(b)["solar_factor"] >= make_profiles(a)["solar_factor"]))

    def test_outage_and_physical_balance(self):
        c = Config(scenario="Grid outage")
        r, _, p = run(c)
        outage = ~p["grid_available"]
        self.assertTrue(np.all(r["grid_import"][outage] == 0))
        self.assertTrue(np.all(r["grid_export"][outage] == 0))
        self.assertFalse(np.any((r["grid_import"] > 0) & (r["grid_export"] > 0)))
        lhs = r["pv"] + r["grid_import"] + r["generator"] + r["discharge"]
        rhs = r["served_critical"] + r["served_flexible"] + r["charge"] + r["grid_export"] + r["curtailed"]
        np.testing.assert_allclose(lhs, rhs, atol=1e-7)

    def test_battery_limits_and_no_simultaneous_operation(self):
        c = Config(scenario="Combined storm")
        r, _, _ = run(c)
        self.assertTrue(np.all(r["soc"] >= c.min_soc * 100 - 1e-8))
        self.assertTrue(np.all(r["soc"] <= c.max_soc * 100 + 1e-8))
        self.assertTrue(np.all(r["charge"] * r["discharge"] == 0))
        self.assertTrue(np.all(r["charge"] <= c.charge_limit_kw))
        self.assertTrue(np.all(r["discharge"] <= c.discharge_limit_kw))

    def test_shortage_is_unserved_not_phantom_supply(self):
        c = Config(scenario="Grid outage", pv_capacity_kw=0, battery_enabled=False, generator_enabled=False)
        r, m, p = run(c)
        self.assertGreater(m["unserved_critical_kwh"], 0)
        np.testing.assert_allclose(r["grid_import"][~p["grid_available"]], 0)

    def test_energy_uses_kw_times_hours_and_reproducible(self):
        c = Config(duration_hours=1, step_minutes=5, variability=True)
        a, m, _ = run(c); b, _, _ = run(c)
        self.assertAlmostEqual(m["pv_kwh"], np.sum(a["pv"]) / 12)
        np.testing.assert_array_equal(a["pv"], b["pv"])

    def test_exports_parse(self):
        c = Config(duration_hours=1); r, _, p = run(c)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(results_csv(r, p, c))))), 12)
        self.assertEqual(json.loads(config_json(c))["config"]["seed"], c.seed)
        storm = Config(scenario="Combined storm")
        self.assertEqual(len(json.loads(config_json(storm))["events"]), 3)

    def test_disabled_generator_and_battery_have_zero_output(self):
        c = Config(generator_enabled=False, battery_enabled=False, scenario="Grid outage")
        r, _, _ = run(c)
        np.testing.assert_allclose(r["generator"], 0)
        np.testing.assert_allclose(r["charge"], 0)
        np.testing.assert_allclose(r["discharge"], 0)

    def test_battery_charge_energy_update_uses_one_way_efficiency(self):
        c = Config(duration_hours=24, initial_soc=.4, min_soc=.2, max_soc=.95, pv_capacity_kw=100,
                   critical_kw=0, flexible_kw=0, grid_limit_kw=0, generator_enabled=False)
        r, _, _ = run(c)
        i = int(np.argmax(r["charge"]))
        eta = c.round_trip_efficiency ** .5
        previous = c.battery_capacity_kwh*c.initial_soc if i == 0 else r["energy"][i-1]
        self.assertAlmostEqual(r["energy"][i], previous + r["charge"][i]*(c.step_minutes/60)*eta, places=7)

    def test_combined_storm_applies_all_components_in_selected_windows(self):
        c = Config(scenario="Combined storm")
        base = make_profiles(c)
        r, _, p = run(c)
        outage = (p["hours"] >= c.outage_start) & (p["hours"] < c.outage_start+c.outage_duration)
        drop = (p["hours"] >= c.solar_drop_start) & (p["hours"] < c.solar_drop_start+c.solar_drop_duration)
        spike = (p["hours"] >= c.spike_start) & (p["hours"] < c.spike_start+c.spike_duration)
        self.assertTrue(np.all(~p["grid_available"][outage]))
        self.assertTrue(np.all(r["pv"][drop] < c.pv_capacity_kw * base["solar_factor"][drop]))
        self.assertTrue(np.all(r["load"][spike] > base["critical_demand"][spike] + base["flexible_demand"][spike]))
        self.assertTrue(any(p["events"][outage]))

    def test_empty_load_metrics_are_finite(self):
        c = Config(critical_kw=0, flexible_kw=0, battery_enabled=False, generator_enabled=False)
        _, m, _ = run(c)
        self.assertTrue(np.isfinite(m["renewable_share"]))

    def test_identical_exogenous_profiles_for_comparison(self):
        c = Config(variability=True, scenario="Combined storm")
        first = apply_scenario(c, make_profiles(c))
        second = apply_scenario(c, make_profiles(c))
        for name in ("hours", "solar_factor", "critical_demand", "flexible_demand", "grid_available", "tariff", "events"):
            np.testing.assert_array_equal(first[name], second[name])

    def test_event_validation_is_horizon_aware(self):
        c = Config(duration_hours=1, scenario="Grid outage", outage_start=.5, outage_duration=.5)
        c.validate()
        c.outage_duration = 1
        with self.assertRaises(ValueError): c.validate()

    def test_surplus_pv_is_accounted_as_charge_export_or_curtailment(self):
        c = Config(critical_kw=0, flexible_kw=0, pv_capacity_kw=100, grid_limit_kw=0, generator_enabled=False)
        r, _, _ = run(c)
        np.testing.assert_allclose(r["pv"], r["charge"] + r["grid_export"] + r["curtailed"], atol=1e-7)

    def test_structured_goal_cannot_bypass_soc_validation(self):
        c = Config()
        updated = apply_goal(c, StructuredGoal(objective="Lowest cost", minimum_soc=.25))
        self.assertEqual(updated.min_soc, .25)
        with self.assertRaises(ValueError): apply_goal(c, StructuredGoal(minimum_soc=1.1))

    def test_csv_records_selected_controller_name(self):
        c = Config(duration_hours=1); r, _, p = run(c)
        rows = list(csv.DictReader(io.StringIO(results_csv(r, p, c, "Optimized"))))
        self.assertTrue(all(row["controller"] == "Optimized" for row in rows))


if __name__ == "__main__":
    unittest.main()
