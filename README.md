# GridPilot

GridPilot is a local, interactive microgrid simulator for synthetic energy scenarios. It is a decision-support prototype only and does not connect to or control electrical equipment. Simulation, dispatch, metrics, and exports run locally without an account, API key, or cloud service.

## Run locally

Requires Python 3.11 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

The transparent rule-based controller works in the simulator package with NumPy. The dashboard additionally uses Streamlit, pandas, and Plotly. Optimized dispatch requires SciPy's mixed-integer solver; if it cannot run, GridPilot reports the failure and keeps the baseline results available.

Run the simulator checks with:

```powershell
python -m unittest discover -s tests -v
```

## Controls and scenarios

The sidebar configures PV, storage, grid and generator limits, critical and flexible loads, optional EV/HVAC demand, battery reserve, tariffs, emissions assumptions, synthetic weather and demand curves, time resolution, random seed, and scenario timing. Available scenarios are normal day, grid outage, solar drop, demand spike, combined storm, low battery at start, and high-price period. Run results can be exported as CSV and the configuration as JSON; upload a JSON configuration and apply it to restore the settings.

The baseline serves critical loads first. PV serves demand before the battery; surplus PV charges storage, and residual demand is supplied by the grid, battery, then generator. During shortages, unserved critical and flexible energy remain visible. Flexible demand combines the flexible, EV, and HVAC groups for dispatch. Grid charging of the battery is not modeled in the baseline.

## Model assumptions

- Time-series profiles are synthetic illustrations, not forecasts or facility measurements. Solar follows a smooth 06:00–18:00 daytime curve, while demand has synthetic morning and evening variation.
- Power is kW, energy is kWh, and energy/cost/emissions totals integrate power over each interval (`kW × hours`).
- The battery uses symmetric one-way charge/discharge efficiency equal to the square root of round-trip efficiency. Stored-energy bounds and power bounds are enforced after every step.
- The baseline prevents simultaneous charge and discharge. The optimizer uses a binary battery mode, hard grid/generator/battery bounds, and explicit load-service variables.
- The optimizer is a mixed-integer cost/emissions dispatch model with large penalties for unserved critical and flexible load. A time limit is applied; infeasible or timed-out solves are surfaced as errors.
- Emissions factors and costs are user-configurable estimates, not authoritative values. Renewable share is PV energy divided by total load energy; values can exceed 100% when load is very small or PV is exported/curtailed.
- Solar output scale is capped at 100% of nameplate for physical PV output; the 0–150% control is accepted for stress profiles but the generated PV remains capped at nameplate.

## Limitations

GridPilot uses grouped critical/flexible demand, simplified generator behavior, no startup/ramp constraints, no thermal effects, and no power-quality or network constraints. Event editing is limited to scenario controls rather than a general event table. The future AI planner interface is intentionally not connected; no chatbot or model provider is implied.
