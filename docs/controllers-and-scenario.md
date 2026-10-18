# Overshoot scenario and the controllers

How the simulated scenario works, what each controller does, and why the combined controller uses less heat. All numbers below come from the twin runs in `scenarios/` and are model results under **assumed** parameters, not measurements of a real building.

## The problem we reproduce

A cold morning pre-heat, then sun and people arrive, the room overshoots, and the ventilation purge works against the radiator. The school pays twice: once for radiator heat and once for the ventilation heating coil.

## The scenario (`scenarios/overshoot.py`)

| Item | Value | Status |
|---|---|---|
| Room | 60 m² classroom, 3 m high, 10 m² south window, one external wall, 3 kW radiator | geometry from `config/params.yaml`; wall, infiltration and heat split assumed |
| Weather | synthetic, repeating: mean 2 °C, ±5 K daily swing, sunrise 6:00, sunset 18:00, peak sun 500 W/m² | assumed |
| Start | room at 17 °C on Monday morning | assumed |
| Length | 3 days (overshoot plot), 5 days (comparisons) | |

### Room model (`twin/room_model.py`)

Two heat stores:

- **Air node (fast, about 11 min):** room air plus furniture.
- **Wall node (slow, about 91 h):** walls, floor and ceiling. It soaks up sun and radiator heat and releases it later. This lag is what lets the room overshoot after the radiator is closed.

### Air-handling unit (`twin/ventilation.py`, `ahu_step`)

Outdoor air passes heat recovery, then a heating coil warms it to a **target** temperature (default: the 21 °C room setpoint). The coil only heats, never cools. `supply_air_temp_C` is the air entering the room, and `q_coil_W` is the ventilation energy.

## Legacy controller (`twin/controller.py`)

- Radiator: fixed timers plus a thermostat (valve opens 0.5 per K below the setpoint), reading the room temperature now.
- Ventilation: on 07:00–16:00, 8 L/s per person plus 0.35 L/s per m². Flow is multiplied by 1.5 ("purge") when the room is at 24 °C or above.
- Coil target: always 21 °C.

Result: the coil keeps heating cold outdoor air to 21 °C while the room is already warm, and the purge moves more of that air. Over 5 days the legacy plant uses 169.9 kWh of heat, about **90 % of it in the coil** (155 kWh). The radiator is already off by day 3. The room peaks at 23.3, 24.55 and 25.06 °C on days 1–3, and is cold at the first Monday lesson (18.4 °C).

## Controller A: forecast heating (`twin/predictive_controller.py`)

Changes the radiator only. It asks the twin to preview the future (`DigitalTwin.preview`, perfect weather forecast and perfect room model):

1. **Optimal start.** Before the school day: "if I heat at full valve from now, does the room just reach 21 °C at the first lesson?" It starts at the latest moment where the answer is yes (at most 6 h before). Cold mornings start earlier, sunny ones later. Otherwise it holds the 17 °C setback.
2. **Look-ahead thermostat.** During the day: "where will the room be in 60 min if the valve closes now?" The valve opens by 0.5 per K that forecast is below 21 °C. Sun, people and stored wall heat therefore close the valve early.

Decisions are made every 5 min. Alone it does not save heat (+2.6 %), but it removes most cold lesson minutes (71 to 6), because the radiator is a small part of the bill.

## Controller B: supply-temperature control (`twin/supply_controller.py`)

Changes only the coil target, based on the room temperature:

```
target = clamp(setpoint − gain × (T_room − setpoint), min_supply, setpoint)
gain = 2 K/K, min_supply = 16 °C, setpoint = 21 °C
```

| Room | Coil target |
|---|---|
| ≤ 21 °C | 21 °C (same as legacy) |
| 22 °C | 19 °C |
| 23 °C | 17 °C |
| ≥ 23.5 °C | 16 °C |

Why it saves heat:

1. The coil heats the air less when the room is warm, so coil energy falls directly.
2. The cooler supply air carries away surplus sun and people heat, so the peak is lower.
3. The room reaches the 24 °C purge trigger less often (purge minutes 2206 to 444), so less air is moved.

In plain terms: the plant stops paying to warm air that then has to cool an already-warm room.

## Combined controller (`scenarios/compare_combined.py`)

`SupplyTempController(ForecastController(...))`. The forecast part previews with the supply control included, so its prediction matches what the plant really does.

| 5 days | Heat | Peak | Lesson minutes below 20 °C |
|---|---|---|---|
| Legacy | 169.9 kWh | 25.45 °C | 71 |
| Forecast heating only | +2.6 % | 25.47 °C | 6 |
| Supply-temp only | −22.3 % | 24.19 °C | 71 |
| **Combined** | **−21.1 %** | **24.19 °C** | **6** |

Supply-temp control brings the saving and the lower peak; forecast heating brings the comfort at the cold start.

## Sensitivity (`scenarios/sensitivity.py`)

26 cases, one assumed value changed at a time (weather, wall U-value, window area, g-value, shading, wall mass, infiltration, heat recovery, pupils, controller settings).

- The combined saving ranges from **−2.4 % to +40.9 %**. It is positive in 25 of 26 cases.
- It is large when legacy overshoots a lot (mild weather, strong sun) and small when it barely overshoots (cold weather 2.6 %, weak sun 2.9 %). With external shading (factor 0.3) there is no overshoot to remove and combined costs 2.4 % more heat.
- The combined controller never raised the peak and never added cold lesson minutes in any case.
- The 70 % heat-recovery case still saves about 27 %, although total heat falls from 170 to 47 kWh.

Outputs: `out/sensitivity.csv`, `out/sensitivity.png`.

## Limits

- Perfect forecast and perfect model: this is a best case. A real controller would do less well.
- Assumed values: all room parameters, the 16 °C minimum, gain 2 K/K, 60 min look-ahead, 6 h maximum pre-heat, 5 min decision interval, and the synthetic repeating weather.
- Draught or discomfort from colder supply air is not modelled.
- No measured indoor temperatures exist (the Oslo dataset has none), so this shows the mechanism, not a proven saving for a real building.

Safe wording: "In a modelled classroom, room-compensated supply-air temperature cut heat by 3–41 % depending on overshoot (21 % in the base case) without adding cold lesson time."

## How to run

```bash
uv run python -m scenarios.overshoot
uv run python -m scenarios.compare_controllers
uv run python -m scenarios.compare_ventilation
uv run python -m scenarios.compare_combined
uv run python -m scenarios.sensitivity       # about 100 s
```

If `uv run` picks system packages, see `pythonpath-note.md`.
