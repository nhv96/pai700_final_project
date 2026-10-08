# Room energy balance (heat-model contract)

Reference for the zone equation used by the digital twin and the heat-model owner. It defines what each term means, its sign, its unit and where it comes from in the code, so both sides work from the same definitions.

Status: **v0.1, draft.** The room equation belongs to the heat-model teammate. The twin only supplies the inputs.

## Equation

```
C · dT_in/dt = Q_radiator + Q_internal + Q_solar − (T_in − T_out) / R − Q_vent
```

Left side: the rate at which the zone's stored heat changes. Right side: the net power flowing into the zone.

## Terms

| Symbol | Meaning | Unit | Sign | Owner / source |
|---|---|---|---|---|
| `T_in` | Zone air temperature (state) | °C | — | Heat model (`ZoneState.t_air_C`) |
| `dT_in/dt` | Rate of change of zone air temperature | K/s | — | Heat model |
| `C` | Zone heat capacity (air, furniture, effective fabric mass) | J/K | > 0 | Heat model. Placeholder in `twin/placeholder_model.py`: 2.2 MJ/K |
| `Q_radiator` | Heat output of the radiator | W | + | Twin (`twin/radiator.py`), from valve position and supply temperature |
| `Q_internal` | Heat from pupils, teachers, lighting and equipment | W | + | Twin (`StepInputs.q_internal_W`) |
| `Q_solar` | Solar gain through windows | W | + | Heat model, from `solar_irradiance_W_m2`. Formula below |
| `T_out` | Outdoor air temperature | °C | — | Twin (`StepInputs.t_outdoor_C`) |
| `R` | Envelope thermal resistance (walls, windows, roof) | K/W | > 0 | Heat model. Placeholder: 0.025 K/W (≈ 40 W/K) |
| `Q_vent` | Heat carried away by ventilation air (net of heat recovery) | W | − (as a loss) | Heat model, from flow, supply air temperature and heat recovery. Formula below |

Sign convention: positive terms add heat to the zone, negative terms remove it.

## Solar gain

```
Q_solar = irradiance × window_area × g_value
```

- `irradiance`: solar irradiance on the window, W/m² (`solar_irradiance_W_m2`).
- `window_area`: m² (`params.yaml`: `zone.window_area_m2`, typical 10 m²).
- `g_value`: solar energy transmittance of the glazing, dimensionless, 0–1 (`params.yaml`: `solar.window_g_value`, typical 0.6).

Shading is not modelled in v0 (`params.yaml`: `window_solar_shading: none`).

## Ventilation loss

```
Q_vent = (1 − heat_recovery_eff) × ρ × cp × flow × (T_in − T_supply_air)
```

- `flow`: volumetric airflow, m³/s. The twin provides L/s (`ventilation_flow_L_s`); divide by 1000.
- `ρ`: air density, 1.2 kg/m³.
- `cp`: specific heat of air, 1005 J/(kg·K).
- `T_supply_air`: temperature of the incoming air, °C. In v0 this is the outdoor temperature (`supply_air_temp_C`).
- `heat_recovery_eff`: heat exchanger efficiency, 0–1 (`heat_recovery_eff`). 0 for a school without heat recovery, 0.6–0.9 with FTX.

Example: 221 L/s, no heat recovery, 10 K difference between room and supply air gives about 2.7 kW.

## Radiator and internal gains (twin side)

- `Q_radiator` comes from `Radiator.step()` in `twin/radiator.py`. It is first-order lagged toward the steady output, so it does not jump instantly when the valve moves.
- `Q_internal` = pupils × 60 W + adults × 75 W + lighting (10 W/m² × floor area) + equipment (200 W). Values are assumed; see `config/params.yaml`.

## Numerical scheme (placeholder)

The placeholder model advances the state with an explicit Euler step:

```
T_new = T_in + (Q_radiator + Q_internal + Q_solar − (T_in − T_out)/R − Q_vent) / C × dt
```

with `dt = 60 s`. The heat-model owner may use a different scheme.

## Open items

- `R`, `C` and the envelope model: heat-model owner to define from the building's construction.
- Whether the model owns `Q_solar` and `Q_vent` as shown, or whether the twin should pass them ready-made. Agree before coding the real model.
- Solar irradiance source and the Trollhättan station are still open (see `docs/parameters.md`).
- Overheat purge (`params.yaml`: `overheat_response`) is a placeholder and does not yet change `Q_vent` in the placeholder model's output.
