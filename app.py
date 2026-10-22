"""GridPilot Streamlit interface. Core dispatch lives in gridpilot/, not in this file."""
import json
from dataclasses import asdict
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from gridpilot.config import Config
from gridpilot.profiles import make_profiles
from gridpilot.scenarios import apply_scenario
from gridpilot.simulator import run
from gridpilot.metrics import summarize
from gridpilot.exports import results_csv, config_json
from gridpilot.controllers.rule_based import dispatch as rule_dispatch


st.set_page_config(page_title="GridPilot | Microgrid simulator", page_icon="⚡", layout="wide")
st.markdown("""<style>
  .block-container {max-width: 1500px; padding-top: 1.4rem;}
  [data-testid="stMetric"] {background:#f4f8f7; border:1px solid #e2ebe8; padding:14px 16px; border-radius:12px;}
  h1 {letter-spacing:-.04em;} .caption {color:#63746f;}
</style>""", unsafe_allow_html=True)

DEFAULTS = Config()
if "last_run" not in st.session_state: st.session_state.last_run = None
if "run_time" not in st.session_state: st.session_state.run_time = None
if "reset_counter" not in st.session_state: st.session_state.reset_counter = 0
suffix = str(st.session_state.reset_counter)


def key(name): return f"{name}_{suffix}"


def set_default(name, value):
    if key(name) not in st.session_state: st.session_state[key(name)] = value


def apply_uploaded_config():
    payload = st.session_state[key("upload")]
    raw = json.loads(payload.getvalue().decode("utf-8"))
    incoming = Config(**raw.get("config", raw))
    mapping = {
        "duration_hours": ("duration", 1), "step_minutes": ("step", 1), "start_hour": ("start_hour", 1),
        "pv_capacity_kw": ("pv", 1), "battery_capacity_kwh": ("batt", 1), "charge_limit_kw": ("charge", 1),
        "discharge_limit_kw": ("discharge", 1), "battery_enabled": ("battery_on", 1), "grid_limit_kw": ("grid", 1),
        "generator_capacity_kw": ("gen_cap", 1), "generator_enabled": ("gen_on", 1), "critical_kw": ("critical", 1),
        "flexible_kw": ("flexible", 1), "ev_enabled": ("ev_on", 1), "ev_kw": ("ev", 1), "hvac_enabled": ("hvac_on", 1),
        "hvac_kw": ("hvac", 1), "initial_soc": ("initial", 100), "min_soc": ("min_soc", 100), "max_soc": ("max_soc", 100),
        "round_trip_efficiency": ("eta", 100), "grid_price": ("grid_price", 1), "export_price": ("export_price", 1),
        "export_enabled": ("export_on", 1), "generator_cost": ("gen_cost", 1), "grid_emissions": ("grid_em", 1),
        "generator_emissions": ("gen_em", 1), "carbon_price": ("carbon", 1), "solar_scale": ("solar", 100),
        "demand_scale": ("demand", 100), "weather": ("weather", 1), "demand_profile": ("demand_profile", 1),
        "variability": ("variability", 1), "seed": ("seed", 1), "scenario": ("scenario", 1), "objective": ("objective", 1), "currency_label": ("currency", 1),
        "outage_start": ("outage_start", 1), "outage_duration": ("outage_dur", 1),
        "solar_drop_start": ("drop_start", 1), "solar_drop_duration": ("drop_dur", 1),
        "solar_drop_percent": ("drop_pct", 1), "spike_start": ("spike_start", 1),
        "spike_duration": ("spike_dur", 1), "spike_percent": ("spike_pct", 1), "spike_loads": ("spike_loads", 1),
    }
    for field, (control, multiplier) in mapping.items(): st.session_state[key(control)] = getattr(incoming, field) * multiplier
    st.session_state[key("target_on")] = incoming.target_soc is not None
    if incoming.target_soc is not None: st.session_state[key("target")] = incoming.target_soc * 100


st.title("⚡ GridPilot")
st.caption("Interactive microgrid simulation and resilience testing  ·  Simulation only — does not control real equipment")

with st.sidebar:
    st.header("System configuration")
    with st.expander("System size", expanded=True):
        pv = st.slider("Solar PV capacity (kW)", 0, 200, int(DEFAULTS.pv_capacity_kw), key=key("pv"))
        batt = st.slider("Battery capacity (kWh)", 10, 500, int(DEFAULTS.battery_capacity_kwh), key=key("batt"))
        charge = st.slider("Battery charge limit (kW)", 0, 200, int(DEFAULTS.charge_limit_kw), key=key("charge"))
        discharge = st.slider("Battery discharge limit (kW)", 0, 200, int(DEFAULTS.discharge_limit_kw), key=key("discharge"))
        battery_on = st.checkbox("Battery enabled", True, key=key("battery_on"))
        grid_limit = st.slider("Grid import limit (kW)", 0, 500, int(DEFAULTS.grid_limit_kw), key=key("grid"))
        gen_cap = st.slider("Generator capacity (kW)", 0, 300, int(DEFAULTS.generator_capacity_kw), key=key("gen_cap"))
        gen_on = st.checkbox("Generator enabled", True, key=key("gen_on"))
        critical = st.slider("Critical demand (kW)", 0, 200, int(DEFAULTS.critical_kw), key=key("critical"))
        flexible = st.slider("Flexible demand (kW)", 0, 200, int(DEFAULTS.flexible_kw), key=key("flexible"))
        ev_on = st.checkbox("Enable EV charging", False, key=key("ev_on"))
        ev = st.slider("EV load (kW)", 0, 100, 0, key=key("ev"), disabled=not ev_on)
        hvac_on = st.checkbox("Enable controllable HVAC", False, key=key("hvac_on"))
        hvac = st.slider("HVAC load (kW)", 0, 100, 0, key=key("hvac"), disabled=not hvac_on)
    with st.expander("Battery settings"):
        initial = st.slider("Starting SOC (%)", 0, 100, 80, key=key("initial"))
        if key("min_soc") in st.session_state: st.session_state[key("min_soc")] = min(st.session_state[key("min_soc")], min(50, initial))
        min_soc = st.slider("Minimum SOC (%)", 0, min(50, initial), min(20, initial), key=key("min_soc"))
        if key("max_soc") in st.session_state: st.session_state[key("max_soc")] = max(st.session_state[key("max_soc")], max(50, initial))
        max_soc = st.slider("Maximum SOC (%)", max(50, initial), 100, max(95, initial), key=key("max_soc"))
        eta = st.slider("Round-trip efficiency (%)", 70, 100, 90, key=key("eta"))
        target_enabled = st.checkbox("Set target SOC at end", False, key=key("target_on"))
        if key("target") in st.session_state: st.session_state[key("target")] = min(max(st.session_state[key("target")], min_soc), max_soc)
        target_soc = st.slider("Target SOC (%)", min_soc, max_soc, int(initial), key=key("target"), disabled=not target_enabled)
        st.caption(f"Estimated starting stored energy: {batt * initial / 100:.1f} kWh")
    with st.expander("Economics and emissions"):
        currency = st.text_input("Currency label", "$", key=key("currency"))
        grid_price = st.number_input("Grid import price / kWh", 0.0, 5.0, .20, .01, key=key("grid_price"))
        export_price = st.number_input("Grid export price / kWh", 0.0, 5.0, .05, .01, key=key("export_price"))
        export_on = st.checkbox("Allow grid export", False, key=key("export_on"))
        gen_cost = st.number_input("Generator operating cost / kWh", 0.0, 10.0, .45, .01, key=key("gen_cost"))
        grid_emissions = st.number_input("Grid emissions estimate (kg CO₂e/kWh)", 0.0, 5.0, .40, .05, key=key("grid_em"))
        gen_emissions = st.number_input("Generator emissions estimate (kg CO₂e/kWh)", 0.0, 10.0, .70, .05, key=key("gen_em"))
        carbon_price = st.slider("Optional carbon cost / kg", 0.0, 10.0, 0.0, .1, key=key("carbon"))
        objective = st.selectbox("Dispatch objective", ["Lowest cost", "Lower emissions", "Balanced", "Maximum resilience"], index=2, key=key("objective"))
        st.caption("Emissions factors are user-configurable estimates, not authoritative values.")
    with st.expander("Weather and demand"):
        solar_pct = st.slider("Solar output scale (%)", 0, 150, 100, key=key("solar"))
        demand_pct = st.slider("Demand scale (%)", 50, 200, 100, key=key("demand"))
        weather = st.selectbox("Weather profile", ["Clear", "Partly cloudy", "Cloudy", "User adjusted"], key=key("weather"))
        demand_profile = st.selectbox("Demand profile", ["Typical day", "High demand", "Low demand", "User adjusted"], key=key("demand_profile"))
        variability = st.checkbox("Reproducible random variability", False, key=key("variability"))
        seed = st.number_input("Random seed", 0, 2**31 - 1, 42, key=key("seed"))
        st.caption("Profiles are synthetic illustrations, not weather forecasts or measured facility demand.")
    with st.expander("Scenario and simulation", expanded=True):
        duration = st.slider("Simulation duration (hours)", 1, 72, 24, key=key("duration"))
        step = st.selectbox("Time step", [1, 5, 10, 15], index=1, format_func=lambda x: f"{x} minute{'s' if x != 1 else ''}", key=key("step"))
        start_hour = st.slider("Start hour / profile offset", 0, 23, 0, key=key("start_hour"))
        controller = st.selectbox("Controller", ["Rule-based baseline", "Optimized dispatch", "Compare both"], key=key("controller"))
        scenario = st.selectbox("Scenario", ["Normal day", "Grid outage", "Solar drop", "Demand spike", "Combined storm", "Low battery at start", "High-price period"], key=key("scenario"))
        scenario_help = {
            "Normal day": "Grid stays available while synthetic solar and demand profiles vary through the day.",
            "Grid outage": "Grid imports and exports are forced to zero during the configured outage window.",
            "Solar drop": "PV output is reduced during a configurable event window.",
            "Demand spike": "Selected load groups increase for a configurable period.",
            "Combined storm": "Combines an outage, reduced solar, and increased demand for a resilience stress test.",
            "Low battery at start": "Starts close to the configured minimum SOC to test reserve conservation.",
            "High-price period": "Raises the grid tariff during the selected window to test storage dispatch.",
        }
        st.caption(scenario_help[scenario])
        horizon_max = max(.25, float(duration) - .25)
        duration_max = min(12.0, float(duration))
        for name in ("outage_start", "drop_start", "spike_start"):
            if key(name) in st.session_state: st.session_state[key(name)] = min(st.session_state[key(name)], horizon_max)
        if scenario in ("Grid outage", "Combined storm"):
            outage_start = st.slider("Outage start (hours)", 0.0, horizon_max, min(12.0, horizon_max), .25, key=key("outage_start"))
            if key("outage_dur") in st.session_state: st.session_state[key("outage_dur")] = min(st.session_state[key("outage_dur")], duration-outage_start)
            outage_dur = st.slider("Outage duration (hours)", .25, min(duration_max, duration-outage_start), min(2.0, duration-outage_start), .25, key=key("outage_dur"))
        else: outage_start, outage_dur = 12.0, 2.0
        if scenario in ("Solar drop", "Combined storm"):
            drop_start = st.slider("Solar drop start (hours)", 0.0, horizon_max, min(11.0, horizon_max), .25, key=key("drop_start"))
            if key("drop_dur") in st.session_state: st.session_state[key("drop_dur")] = min(st.session_state[key("drop_dur")], duration-drop_start)
            drop_dur = st.slider("Solar drop duration (hours)", .25, min(duration_max, duration-drop_start), min(3.0, duration-drop_start), .25, key=key("drop_dur"))
            drop_pct = st.slider("Solar reduction (%)", 0, 100, 70, key=key("drop_pct"))
        else: drop_start, drop_dur, drop_pct = 12.0, 3.0, 70.0
        if scenario in ("Demand spike", "Combined storm", "High-price period"):
            spike_start = st.slider("Demand spike / tariff window start (hours)", 0.0, horizon_max, min(17.0, horizon_max), .25, key=key("spike_start"))
            if key("spike_dur") in st.session_state: st.session_state[key("spike_dur")] = min(st.session_state[key("spike_dur")], duration-spike_start)
            spike_dur = st.slider("Demand spike / tariff duration (hours)", .25, min(duration_max, duration-spike_start), min(2.0, duration-spike_start), .25, key=key("spike_dur"))
            spike_pct = st.slider("Demand increase (%)", 0, 200, 50, key=key("spike_pct"))
            spike_loads = st.multiselect("Loads affected", ["Critical", "Flexible", "EV", "HVAC"], ["Critical", "Flexible"], key=key("spike_loads"))
        else: spike_start, spike_dur, spike_pct, spike_loads = 17.0, 2.0, 50.0, ["Critical", "Flexible"]
    if st.button("Reset to defaults", use_container_width=True):
        st.session_state.reset_counter += 1
        st.session_state.last_run = None
        st.rerun()
    uploaded = st.file_uploader("Load scenario JSON", type=["json"], key=key("upload"))
    if uploaded:
        try:
            data = json.loads(uploaded.getvalue().decode("utf-8"))
            candidate = Config(**data.get("config", data))
            candidate.validate()
            st.button("Apply loaded configuration", key=key("apply_json"), on_click=apply_uploaded_config)
        except (ValueError, TypeError, UnicodeDecodeError): st.error("This file is not valid GridPilot JSON.")

target = float(target_soc) / 100 if target_enabled else None
cfg = Config(duration_hours=duration, step_minutes=step, start_hour=start_hour, pv_capacity_kw=pv, solar_scale=solar_pct/100,
    battery_capacity_kwh=batt, charge_limit_kw=charge, discharge_limit_kw=discharge, initial_soc=initial/100,
    min_soc=min_soc/100, max_soc=max_soc/100, round_trip_efficiency=eta/100, battery_enabled=battery_on,
    grid_limit_kw=grid_limit, export_enabled=export_on, grid_export_limit_kw=grid_limit if export_on else 0,
    grid_price=grid_price, export_price=export_price, grid_emissions=grid_emissions, generator_capacity_kw=gen_cap,
    generator_enabled=gen_on, generator_cost=gen_cost, generator_emissions=gen_emissions,
    critical_kw=critical, flexible_kw=flexible, ev_enabled=ev_on, ev_kw=ev, hvac_enabled=hvac_on, hvac_kw=hvac,
    demand_scale=demand_pct/100, weather=weather, demand_profile=demand_profile, variability=variability, seed=int(seed),
    objective=objective, currency_label=currency, carbon_price=carbon_price, target_soc=target, scenario=scenario,
    outage_start=outage_start, outage_duration=outage_dur, solar_drop_start=drop_start, solar_drop_duration=drop_dur,
    solar_drop_percent=drop_pct, spike_start=spike_start, spike_duration=spike_dur, spike_percent=spike_pct, spike_loads=spike_loads)

if st.button("▶ Run simulation", type="primary"):
    try:
        with st.spinner("Running simulation and checking system constraints…"):
            cfg.validate()
            profiles = apply_scenario(cfg, make_profiles(cfg))
            baseline = rule_dispatch(cfg, profiles)
            results = {"Rule-based": baseline}
            errors = []
            if controller in ("Optimized dispatch", "Compare both"):
                try:
                    from gridpilot.controllers.optimized import dispatch as optimized_dispatch
                    results["Optimized"] = optimized_dispatch(cfg, profiles)
                except RuntimeError as exc: errors.append(str(exc))
        st.session_state.last_run = {"config": cfg.to_dict(), "results": results, "profiles": profiles, "errors": errors,
                                     "selected_controller": controller, "currency": currency}
        st.session_state.run_time = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    except ValueError as exc: st.error(str(exc))

snapshot = st.session_state.last_run
st.markdown(f"**Status:** {'Simulation complete' if snapshot else 'Ready'}")
if snapshot is None:
    st.info("Configure the system and scenario in the sidebar, then run a simulation to explore power flows and resilience.")
else:
    edited_config = cfg.to_dict()
    if snapshot["config"]["scenario"] == "Low battery at start": edited_config["initial_soc"] = snapshot["config"]["initial_soc"]
    stale = snapshot["config"] != edited_config or snapshot["selected_controller"] != controller
    low_soc_note = f" · low-battery scenario started at {snapshot['config']['initial_soc']*100:.0f}% SOC" if snapshot["config"]["scenario"] == "Low battery at start" else ""
    st.caption(f"Last run: {st.session_state.run_time} · {snapshot['config']['scenario']} · {snapshot['config']['duration_hours']} h · {snapshot['config']['step_minutes']} min steps" + low_soc_note + (" · Displayed results are from the last run; settings have changed." if stale else ""))
    if snapshot["errors"]:
        for err in snapshot["errors"]: st.warning(err)
    selected_name = "Optimized" if snapshot["selected_controller"] == "Optimized dispatch" and "Optimized" in snapshot["results"] else "Rule-based"
    results = snapshot["results"]
    if selected_name not in results: selected_name = "Rule-based"
    result = results[selected_name]
    metrics = summarize(result, Config(**snapshot["config"]))
    st.subheader("Simulation results")
    cols = st.columns(4)
    cards = [("Total load", f"{metrics['load_kwh']:.1f} kWh"), ("PV generated", f"{metrics['pv_kwh']:.1f} kWh"),
             ("Grid imported", f"{metrics['grid_kwh']:.1f} kWh"), ("Generator output", f"{metrics['generator_kwh']:.1f} kWh"),
             ("Operating cost", f"{snapshot['currency']}{metrics['cost']:.2f}"), ("Emissions estimate", f"{metrics['emissions_kg']:.1f} kg CO₂e"),
             ("Unserved critical", f"{metrics['unserved_critical_kwh']:.2f} kWh"), ("Battery SOC min / end", f"{metrics['min_soc']:.1f}% / {metrics['final_soc']:.1f}%")]
    for i, (label, value) in enumerate(cards): cols[i % 4].metric(label, value)
    if metrics["unserved_critical_kwh"] > 0:
        st.warning("Critical demand exceeded available supply during part of this scenario. Unserved critical energy is shown in the reliability plot.")
    t = result["time"]
    def chart_base(title, ytitle):
        fig = go.Figure(); fig.update_layout(title=title, xaxis_title="Hours from simulation start", yaxis_title=ytitle,
            hovermode="x unified", height=390, margin=dict(l=15,r=15,t=55,b=15), legend=dict(orientation="h", y=-.25))
        for i, event in enumerate(result["events"]):
            if event and (i == 0 or result["events"][i-1] != event):
                j = i
                while j + 1 < len(t) and result["events"][j+1] == event: j += 1
                fig.add_vrect(x0=t[i], x1=t[j] + snapshot["config"]["step_minutes"]/60, fillcolor="#f5b942", opacity=.12, line_width=0, annotation_text=event if j-i > 1 else "")
        return fig
    left, right = st.columns(2)
    with left:
        fig = chart_base("Power flow", "Power (kW)")
        for keyname, label, color in [("pv","PV available","#e2a82e"),("critical_demand","Critical demand","#cf5966"),("flexible_demand","Flexible demand","#ec9d72"),("grid_import","Grid import","#4185a5"),("generator","Generator","#8268a8"),("charge","Battery charge","#36a389"),("discharge","Battery discharge","#216e58"),("grid_export","Grid export","#8ab5a6")]:
            fig.add_trace(go.Scatter(x=t,y=result[keyname],name=label,line=dict(color=color,width=2)))
        fig.add_trace(go.Scatter(x=t,y=result["load"],name="Total load",line=dict(color="#6e7473",dash="dot")))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        fig = chart_base("Battery and reliability", "SOC (%) / unserved power (kW)")
        fig.add_trace(go.Scatter(x=t,y=result["soc"],name="Battery SOC (%)",line=dict(color="#167a63",width=3),yaxis="y"))
        fig.add_hline(y=snapshot["config"]["min_soc"]*100,line_dash="dash",line_color="#cf5966",annotation_text="Minimum SOC")
        fig.add_trace(go.Scatter(x=t,y=result["unserved_critical"],name="Unserved critical (kW)",fill="tozeroy",line=dict(color="#c44555"),yaxis="y2"))
        fig.add_trace(go.Scatter(x=t,y=result["unserved_flexible"],name="Unserved flexible (kW)",line=dict(color="#e6a45d"),yaxis="y2"))
        fig.update_layout(yaxis2=dict(title="Unserved power (kW)", overlaying="y", side="right", rangemode="tozero"))
        st.plotly_chart(fig, use_container_width=True)
    left, right = st.columns(2)
    with left:
        cumulative = np.cumsum(result["cost"])
        fig = chart_base("Cumulative operating cost", f"Cost ({snapshot['currency']})")
        fig.add_trace(go.Scatter(x=t,y=cumulative,name="Cumulative cost",line=dict(color="#417ea3",width=3)))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Energy contribution")
        dt = snapshot["config"]["step_minutes"] / 60
        source = pd.DataFrame({"Source": ["PV", "Grid", "Generator", "Battery discharge"], "Energy (kWh)": [np.sum(result[k])*dt for k in ("pv", "grid_import", "generator", "discharge")]})
        fig = go.Figure(go.Bar(x=source["Source"], y=source["Energy (kWh)"], marker_color=["#e2a82e","#4185a5","#8268a8","#36a389"]))
        fig.update_layout(height=300, yaxis_title="Energy (kWh)", margin=dict(l=10,r=10,t=25,b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Estimated emissions: grid {np.sum(result['grid_import'])*dt*snapshot['config']['grid_emissions']:.1f} kg CO₂e · generator {np.sum(result['generator'])*dt*snapshot['config']['generator_emissions']:.1f} kg CO₂e. Renewable share = PV energy / total load energy.")
        grid_cost = np.sum(result["grid_import"] * snapshot["profiles"]["tariff"]) * dt
        generator_cost = np.sum(result["generator"]) * dt * snapshot["config"]["generator_cost"]
        export_revenue = np.sum(result["grid_export"]) * dt * snapshot["config"]["export_price"]
        st.caption(f"Cost estimate by source: grid {snapshot['currency']}{grid_cost:.2f} · generator {snapshot['currency']}{generator_cost:.2f} · export credit −{snapshot['currency']}{export_revenue:.2f}.")
    if snapshot["selected_controller"] == "Compare both":
        st.subheader("Controller comparison")
        rows = []
        for name, r in results.items():
            m = summarize(r, Config(**snapshot["config"]))
            rows.append({"Controller": name, "Cost": m["cost"], "Unserved critical (kWh)": m["unserved_critical_kwh"], "Unserved flexible (kWh)": m["unserved_flexible_kwh"], "Emissions (kg CO₂e)": m["emissions_kg"], "Minimum SOC (%)": m["min_soc"], "Final SOC (%)": m["final_soc"]})
        st.dataframe(pd.DataFrame(rows).set_index("Controller"), use_container_width=True)
        if len(rows) == 2:
            a, b = rows
            findings = []
            if abs(a["Cost"]) > 1e-12:
                change = (a["Cost"]-b["Cost"])/a["Cost"]*100
                findings.append(f"optimized dispatch {'reduced' if change >= 0 else 'increased'} cost by {abs(change):.1f}%")
            else: findings.append("baseline cost is zero, so percentage cost change is undefined")
            if b["Unserved critical (kWh)"] > a["Unserved critical (kWh)"] + 1e-9: findings.append("it left more critical energy unserved")
            elif b["Unserved critical (kWh)"] < a["Unserved critical (kWh)"] - 1e-9: findings.append("it left less critical energy unserved")
            if b["Emissions (kg CO₂e)"] < a["Emissions (kg CO₂e)"] - 1e-9: findings.append("estimated emissions were lower")
            elif b["Emissions (kg CO₂e)"] > a["Emissions (kg CO₂e)"] + 1e-9: findings.append("estimated emissions were higher")
            if b["Final SOC (%)"] < a["Final SOC (%)"] - .1: findings.append("final battery reserve was lower")
            elif b["Final SOC (%)"] > a["Final SOC (%)"] + .1: findings.append("final battery reserve was higher")
            st.info("Compared with baseline, " + "; ".join(findings) + ". These results show trade-offs across the same scenario.")
    st.download_button("Download results CSV", results_csv(result, snapshot["profiles"], Config(**snapshot["config"]), selected_name), "gridpilot-results.csv", "text/csv")
    st.download_button("Download run configuration JSON", config_json(Config(**snapshot["config"])), "gridpilot-scenario.json", "application/json")

