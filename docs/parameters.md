# Parameter research v0.1: classroom digital twin (Swedish school)

Scope: one classroom zone, 60 s step, ideal sensors. The heat model (room equation, R and C) is a blackbox owned by the teammate. Everything below is the data the twin feeds into it and around it. The machine-readable version is `params.yaml`.

Confidence: **sourced** = public source, **derived** = calculated from sourced numbers, **assumed** = engineering default, not verified, **unknown** = not found.

## 1. Key parameters

| Group | Parameter | Value (range) | Confidence | Source |
|---|---|---|---|---|
| Zone | Floor area / height / volume | 60 m² / 3.0 m / 180 m³ | assumed | engineering default |
| Zone | Window area, orientation | 10 m² (6–14), south | assumed | engineering default |
| Zone | Solar shading | none (≈3/4 of schools lack it; good shading cuts solar heat up to 90%) | sourced | SKR 2011 |
| Occupancy | Pupils + teacher | 25 (20–30) + 1 | assumed | engineering default |
| Occupancy | School days per year | 165 | sourced | SKR 2011 |
| Occupancy | Daily blocks | 08:00–09:30, 09:45–11:30, 12:30–15:00 | assumed | typical day, replace with real timetable |
| Gains | Sensible heat per pupil / adult | 60 W (50–70) / 75 W (70–90) | assumed | check EN 16798-1 / ISO 7730 |
| Gains | CO₂ per child | 404 mg/min | sourced (secondary) | classroom CO₂ study, essd-487 |
| Gains | Lighting | 10 W/m² (8–20) | derived | SKR 2011 Risbroskolan: ~1200 W per classroom before, −55% after |
| Gains | Teacher PC + projector | 200 W (100–300) | assumed | engineering default |
| Ventilation | Airflow | 8 L/s per person + 0.35 L/s per m² ≈ 221 L/s (≈4.4 ACH) | sourced / derived | AIVC 1992 Växjö case study; SKR 2011 (BBR table) |
| Ventilation | Operating hours | 3500 h/yr average, 1320–2000 h needed | sourced | SKR 2011 |
| Ventilation | Heat recovery | 0 (older school) or 0.6–0.9 (FTX) | sourced | SKR 2011 |
| Ventilation | Overheat purge | triggers at 24 °C, flow ×1.5 | assumed | placeholder for the "system fighting" effect |
| Comfort | Setpoint / lower / discomfort | 21 °C (20–21) / 20 °C / 26 °C | sourced | SKR 2011 |
| Comfort | Cost per °C | ≈5% of heating cost | sourced | SKR 2011 |
| Heating | Supply / return at design outdoor temp | 64 °C / 42 °C at −16 °C (mean of 109 systems) | sourced | Chalmers radiator survey (Jangsten, 2017) |
| Heating | Supply when outdoor ≥ 5 °C | ≤ 55 °C | sourced | same survey |
| Heating | Radiator design supply | 80 °C pre-1980; ≤ 60 °C post-1982 | sourced | same survey |
| Heating | Radiator rated output | 3 kW (2–4.5), confirmed as working value | assumed (user-confirmed) | ~50 W/m²; heat-loss owner should check it covers the design heat loss |
| Heating | Heat price | 1.10–1.35 SEK/kWh | sourced | team's own background doc |
| Actuator | Smart TRV | Zigbee 3.0, M30×1.5, 8–28 °C, valve-% control (Shelly BLU TRV V2), PI (Salus), battery ≈ 2 yrs | sourced | product pages |
| Actuator | TRV price | ≈ GBP 26–58 / USD 30 retail; mechanical TRV retrofit 100–300 SEK | sourced | retailers; SKR 2011 |
| Actuator | Time to move full stroke | not found | unknown | keep configurable |
| Sensor | CO₂ (SCD41) | ±(40 ppm + 5%), 400–5000 ppm | sourced | Sensirion via retailer pages |
| Sensor | Temperature | ≈ ±0.4–0.8 °C (sources differ); SHT4x suggested for accuracy | sourced | esp32.co.uk |
| Weather | Source | SMHI Open Data, hourly, CC BY 4.0, no key | sourced | SMHI / wetterdienst docs |
| Weather | Nearest station | Trollhättan–Vänersborg Airport, 58.314 N, 12.347 E, 40 m; SMHI id not yet resolved | sourced / open | meteo365 METAR page |

## 2. Validation benchmarks

| Benchmark | Value | Source |
|---|---|---|
| Average school heat use (2006) | 152 kWh/m²·yr | SKR 2011, citing STIL2 |
| Average school total energy | 213 kWh/m²·yr (report also says 216) | SKR 2011 |
| Average school size and pupils | just under 5000 m², 325 pupils | SKR 2011 |
| Operations optimisation saving | 10–30% | SKR 2011 |
| Schools with air-climate problems | nearly 75%, temperature most common | SKR 2011 |
| Implied classroom heat use | ≈ 9.1 MWh/yr (152 × 60 m²) | derived |

Use these to check the full twin once the heat model is plugged in. The 2006 numbers are old, so treat them as order of magnitude.

## 3. Interface contract with the teammate

```
StepInputs  (from twin to model, every 60 s)
  t_outdoor_C, solar_irradiance_W_m2,
  occupants, q_internal_W (people + lighting + equipment),
  q_radiator_W,   # computed by the twin
  ventilation_flow_L_s, supply_air_temp_C, heat_recovery_eff

ZoneState   (from model to twin)
  t_air_C                      # required
  anything else the model needs stays inside its own state object
```

**Decisions (2026-10-08):**

- The radiator stays on the twin side. The twin computes `q_radiator_W` from valve position and `t_supply_C` and passes it to the heat model. The model does not compute radiator output.
- Radiator rated output of 3 kW is accepted as the working value. It is still an assumption, so the heat-loss owner should check it covers the room's design heat loss.

## 4. Open items and caveats

- **Assumed values** (zone size, pupils, gains per person, schedule, radiator size, overheat-purge numbers) are placeholders. Nothing in the source set pins them down for a Trollhättan school.
- **SMHI station id** for Trollhättan is not resolved. Use `smhi-open-data` `get_closest_station(58.314, 12.347)`.
- **Solar radiation source** is not verified (SMHI STRÅNG is a candidate, Open-Meteo is the fallback).
- **Design outdoor temperature** −16 °C comes from the Gothenburg survey. Confirm the Trollhättan value.
- **TRV motion speed** and heat meter specs were not found.
- **Source quality:** most Swedish school numbers come from one 2011 SKR report summarising a 2006 survey, and the CO₂ generation figure is from a secondary source. For the final report, cite the originals (Energimyndigheten STIL2 report ER 2007:11, Jangsten 2017).

## Sources

- SKR (2011), *Vägen till energieffektiva skolor*: https://webbutik.skr.se/download/18.550f5b1717d613c0313559a2/1638804157459/7164-649-1.pdf
- Jangsten, *Survey of radiator temperatures in buildings supplied by district heating*, Chalmers: https://research.chalmers.se/publication/252325
- AIVC, *Improved indoor environment and ventilation in schools, Växjö*: https://www.aivc.org/node/19305
- AIVC, ASHRAE classroom ventilation model: https://www.aivc.org/sites/default/files/airbase_5617.pdf
- SBUF 13290, *Energy use in low-energy schools*: https://vpp.sbuf.se/Public/Documents/ProjectDocuments/985696d3-fc4b-4b25-b425-4fb640eeefe1/FinalReport/SBUF_13290_Sammanfattning_Energianvändning_lågenergiskolor (1).pdf
- SMHI Open Data via wetterdienst docs: https://wetterdienst.readthedocs.io/en/latest/data/provider/smhi/observation/index.html
- smhi-open-data (PyPI): https://pypi.org/project/smhi-open-data
- Trollhättan–Vänersborg Airport station: https://meteo365.es/weather-stations/metar/ESGT/
- SCD41 vs SCD40/SCD30: https://esp32.co.uk/scd30-vs-scd40-vs-scd41-which-co%E2%82%82-sensor-wins/
- Shelly BLU TRV V2: https://www.domadoo.fr/en/smart-home-products/9974-shelly-blu-trv-v2-bluetooth-and-zigbee-thermostatic-radiator-valve-3800238074746.html
- Salus TRV3RF: https://qualityheating.co.uk/products/salus-trv3rf-smart-thermostatic-radiator-valve-zigbee-3-0-battery-powered-super-quiet-trv-head
- Sonoff TRVZB: https://www.robotshop.com/products/sonoff-zigbee-30-smart-thermostatic-radiator-valve-trvzb
- NodOn Zigbee TRV: https://tiloli.com/products/tete-de-vanne-thermostatique-zigbee
